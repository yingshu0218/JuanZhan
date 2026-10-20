import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeDocument } from '../src/documentSummary.js';
const p = text => ({ type:'paragraph',text });
const h = (text,level=1) => ({ type:'heading',text,structure:{level} });
function data(items,total=items.length) { return { total,body:items.map((item,index)=>({id:'b'+index,index,...item})) }; }
test('course facts use explicit opening price, not business quote examples or target-account audience',()=>{
  const result=summarizeDocument(data([p('AI漫剧商业实战营'),p('6节直播课 · 12小时 · 1980元'),h('一、掌握的硬技能'),h('1. AI漫剧全流程创作能力',2),h('2. 平台运营能力',2),p('账号定位：确定账号的目标受众'),h('二、接单变现能力'),p('报价参考：200-500元/集，企业级5000元/集'),p('收入预期：10000元')]),'课程.docx');
  assert.deepEqual(result.facts.price.values,['1980元']);
  assert.deepEqual(result.facts.duration.values,['12小时']);
  assert.deepEqual(result.facts.sessions.values,['6节直播课']);
  assert.deepEqual(result.facts.audience.values,[]);
  assert.equal(result.missing,'未说明');
  assert.deepEqual(result.facts.content.values,['AI漫剧全流程创作能力','平台运营能力','接单变现能力']);
  assert.ok(result.summary.includes('1980元'));
  assert.ok(!result.summary.includes('5000'));
  assert.equal(result.facts.price.sources[0].index,1);
});
test('explicit later audience section is retained after an earlier course-content section',()=>{
  const result=summarizeDocument(data([h('课程内容'),h('摄影基础',2),h('适合人群'),p('有基础的摄影爱好者'),{type:'list_item',text:'希望学习布光的创作者'}]));
  assert.deepEqual(result.facts.audience.values,['有基础的摄影爱好者','希望学习布光的创作者']);
});
test('conflicting or conditional labelled fees remain separate and preserve four decimal source strings',()=>{
  const result=summarizeDocument(data([p('课程价格：1980.5600元'),p('报名价格：早鸟1680元'),p('适合人群：内容创作者')]));
  assert.deepEqual(result.facts.price.values,['1980.5600元','早鸟1680元']);
  assert.equal(result.facts.price.sources.length,2);
  assert.deepEqual(result.facts.audience.values,['内容创作者']);
});
test('partial input never asserts that the entire document omitted a field',()=>{
  const result=summarizeDocument(data([h('项目规划'),p('这是一份项目说明。')],250),'项目.docx');
  assert.equal(result.partial,true);
  assert.equal(result.missing,'当前读取范围未说明');
  assert.deepEqual(result.facts.price.values,[]);
  assert.equal(result.course,false);
});
test('unrelated budget, shot length and commercial example rates do not become course facts',()=>{
  const result=summarizeDocument(data([h('课程大纲'),p('广告预算：5000元'),p('视频镜头长度为5分钟'),p('报价参考：价格：200元/集')]));
  assert.deepEqual(result.facts.price.values,[]);
  assert.deepEqual(result.facts.duration.values,[]);
  assert.deepEqual(result.facts.audience.values,[]);
});
test('a document title heading still permits explicit opening logistics, without taking video length',()=>{
  const result=summarizeDocument(data([h('剪辑实战营'),p('6节直播课 · 12小时 · 1980元'),p('视频时长：5分钟'),h('课程内容',2),h('脚本设计',3)]));
  assert.deepEqual(result.facts.price.values,['1980元']);
  assert.deepEqual(result.facts.duration.values,['12小时']);
  assert.equal(result.title,'剪辑实战营');
});
test('price ranges, per-person units and conditional fee descriptions are not reduced to one amount',()=>{
  const result=summarizeDocument(data([p('课程价格：早鸟1280-1980元/人，按班次收费'),p('课次：第12节课程讲剪辑')]));
  assert.deepEqual(result.facts.price.values,['早鸟1280-1980元/人，按班次收费']);
  assert.deepEqual(result.facts.sessions.values,[]);
});
