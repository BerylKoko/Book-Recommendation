import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {JSDOM} from 'jsdom';
import {rankBooks, parseTropeQuery} from '../book-recommendation/static/recommend.js';

const candidate = (id, matches, extra={}) => ({id,title:id,authors:'Author',authorNames:['Author'],conceptMatches:matches,year:2023,...extra});

test('full matches outrank partials; evidence wins over repeated aliases', () => {
 const rows=rankBooks([candidate('partial',['mm','sports'],{aliasMatchCount:100}),candidate('full',['mm','sports','college'])],{id:'seed'},['mm','sports','college']);
 assert.equal(rows[0].id,'full'); assert.equal(rows[1].matchCount,2);
});
test('same book from another provider, author filters, and publication era work', () => {
 const seed={id:'/works/OL1W',authorNames:['C. E. Ricci']};
 const rows=[candidate('google:seed',['mm'],{alternateIds:['/works/OL1W']}),candidate('same-author',['mm'],{authorNames:['C. E. Ricci']}),candidate('other',['mm'])];
 assert.deepEqual(rankBooks(rows,seed,['mm']).map(b=>b.id),['other']);
 assert.equal(rankBooks(rows,seed,['mm'],{newAuthor:false}).length,2);
 assert.equal(rankBooks(rows,seed,['mm'],{era:'classic'}).length,0);
 assert.equal(rankBooks([candidate('unknown',['mm'],{year:null})],seed,['mm'],{era:'recent'}).length,0);
});
test('explicit trope shortcut leaves ordinary book titles alone', () => {
 assert.deepEqual(parseTropeQuery('mm+sports+college'),['mm','sports','college']);
 assert.deepEqual(parseTropeQuery('M/M + hockey + university'),['M/M','hockey','university']);
 assert.equal(parseTropeQuery("Power Plays + Straight A's"),null);
 assert.equal(parseTropeQuery('Iced Out'),null);
});

test('DOM flow: search, seed, tags, pages, evidence links, and persistent reading list', async () => {
 const html=await readFile(new URL('../book-recommendation/templates/index.html',import.meta.url),'utf8');
 const source=(await readFile(new URL('../book-recommendation/static/books.js',import.meta.url),'utf8')).replace(/^import .*?;\n/,'');
 const dom=new JSDOM(html,{url:'http://localhost/',runScripts:'outside-only'});
 const w=dom.window;
 w.HTMLElement.prototype.scrollIntoView=function(){};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 w.HTMLDialogElement.prototype.close=function(){this.open=false};
 w.rankBooks=rankBooks; w.parseTropeQuery=parseTropeQuery;
 const seed=candidate('google:seed',[],{title:'Tempting Venom',authors:'Rina Kent',authorNames:['Rina Kent'],subjects:['mm','sports','college']});
 const books=Array.from({length:18},(_,i)=>candidate(`google:book-${i}`,['mm','sports','college'],{subjects:['mm','sports','college'],url:'https://example.org/book',conceptEvidence:{mm:{note:'A male/male romance.',url:'https://example.org/evidence'}}}));
 const calls=[];
 const live=process.env.BOOKMATCH_TEST_URL;
 w.fetch=async path => {
   calls.push(path);
   if(live) return fetch(live+path);
   return {ok:true,json:async()=>path.startsWith('/api/books') ? {books:[seed],total:1,limit:12} : {books,exactCount:18}};
 };
 w.eval(source);
 const $=selector=>w.document.querySelector(selector);
 const settled=async()=>{
   const deadline=Date.now()+15000;
   while($('#books').getAttribute('aria-busy')==='true' && Date.now()<deadline) await new Promise(resolve=>setTimeout(resolve,20));
   assert.notEqual($('#books').getAttribute('aria-busy'),'true','request completed');
 };
 $('#query').value='Tempting Venom';
 $('#search-form').dispatchEvent(new w.Event('submit',{cancelable:true}));
 await settled();
 assert.ok($('.choose'),'title search returns a usable seed');
 $('.choose').click();
 assert.equal($('#preferences').hidden,false);
 [...w.document.querySelectorAll('#traits input')].forEach(input=>input.checked=['mm','sports','college'].includes(input.value));
 $('#new-author').checked=false;
 $('#recommend').click(); await settled();
 const firstPage=[...w.document.querySelectorAll('.book h3')].map(el=>el.textContent);
 assert.equal(firstPage.length,12);
 assert.equal($('#more').hidden,false);
 assert.ok($('#status').textContent.includes('full matches'));
 $('.details').click();
 assert.equal($('#detail').open,true);
 assert.ok($('#detail-body a').href.startsWith('https://'));
 assert.ok($('#detail-body').textContent.includes('Why these subjects match'));
 $('#save-book').click();
 assert.equal($('#count').textContent,'1');
 const stored=w.localStorage.getItem('bookmatch:reading-list:v1');
 $('#close').click();
 $('#more').click();
 const secondPage=[...w.document.querySelectorAll('.book h3')].map(el=>el.textContent);
 assert.ok(secondPage.length);
 assert.equal(secondPage.some(title=>firstPage.includes(title)),false);
 $('#previous').click();
 assert.deepEqual([...w.document.querySelectorAll('.book h3')].map(el=>el.textContent),firstPage);
 $('#saved').click();
 assert.equal(w.document.querySelectorAll('.book').length,1);
 const reload=new JSDOM(html,{url:'http://localhost/',runScripts:'outside-only'});
 reload.window.localStorage.setItem('bookmatch:reading-list:v1',stored);
 reload.window.rankBooks=rankBooks; reload.window.parseTropeQuery=parseTropeQuery;
 reload.window.eval(source);
 assert.equal(reload.window.document.querySelector('#count').textContent,'1');
 reload.window.close();
 $('#query').value='mm+sports+college';
 $('#search-form').dispatchEvent(new w.Event('submit',{cancelable:true})); await settled();
 assert.ok(calls.at(-1).includes('subject=mm&subject=sports&subject=college'));
 assert.ok($('#status').textContent.includes('18 full matches'));
 $('#custom-trait').value='<img src=x onerror=alert(1)>';
 $('#add-trait').click();
 assert.equal($('#traits img'),null);
 assert.ok($('#preference-status').textContent.includes('up to 3'));
 dom.window.close();
});
