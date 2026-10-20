import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeDocument } from '../src/documentSummary.js';
const p = text => ({ type:'paragraph', text });
const h = (text, level=1) => ({ type:'heading', text, structure:{level} });
function data(items,total=items.length) { return { total,body:items.map((item,index)=>({id:'b'+index,index,...item})) }; }
test('course text uses ordinary ordered points without specialized facts',()=>{
 const result=summarizeDocument(data([p('AI漫剧商业实战营'),p('学员能获得什么'),p('6节直播课 · 12小时 · 1980元'),h('掌握的硬技能'),h('脚本设计',2),p('学会设计脚本。'),h('平台运营',2),h('接单变现'),p('报价参考：200-500元/集')]),'课程.docx');
 assert.equal(result.title,'课程'); assert.equal(result.facts,undefined); assert.equal(result.course,undefined);
 assert.ok(result.points[0].details[0].includes('1980元'));
 assert.deepEqual(result.points.slice(1).map(point=>point.label),['掌握的硬技能','接单变现']);
 assert.ok(result.points[1].details[0].includes('平台运营'));
 assert.ok(result.points[1].sources.some(source=>source.text==='平台运营'));
 assert.ok(!JSON.stringify(result).includes('适合人群'));
});
test('report title wraps sections; representative source sentences carry actual content',()=>{
 const result=summarizeDocument(data([h('项目报告'),p('本季度完成系统迁移。'),h('进展',2),p('完成三个服务的迁移。后续进入维护阶段。'),h('风险',2),p('风险：存量数据仍需抽样核验。')]),'报告.pdf');
 assert.deepEqual(result.points.map(point=>point.label),['项目报告','进展','风险']);
 assert.equal(result.points[1].details[0],'完成三个服务的迁移。');
 assert.equal(result.points[2].index,4);
});
test('unstructured meeting prose and lists remain ordered generic points',()=>{
 const result=summarizeDocument(data([p('讨论接口调整。确认周五交付。'),{type:'list_item',text:'李明负责测试。'},p('费用：早鸟1280-1980元/人，按班次收费')]),'会议纪要.txt');
 assert.equal(result.points.length,4); assert.equal(result.points[1].details[0],'确认周五交付。');
 assert.equal(result.points[3].details[0],'费用：早鸟1280-1980元/人，按班次收费');
});
test('uneven chapter levels retain the first chapter name and its source',()=>{
 const result=summarizeDocument(data([h('第一章'),p('书籍第一段。'),h('第二章',2),p('书籍第二段。')]));
 assert.deepEqual(result.points.map(point=>point.label),['第一章','第二章']);
 assert.equal(result.points[0].details[0],'书籍第一段。');
 assert.equal(result.points[0].sources[0].index,0);
});
test('table excerpts preserve actual column labels, values and source navigation',()=>{
 const result=summarizeDocument(data([h('设备清单'),{type:'table',text:'',structure:{table:{headers:['设备','状态'],rows:[['主机','已验收'],['路由器','待验证']]}}}]));
 assert.ok(result.points[0].details[0].includes('设备：主机；状态：已验收'));
 assert.equal(result.points[0].sources[1].index,1);
 const withHeaderRow=summarizeDocument(data([h('清单'),{type:'table',structure:{table:{rows:[['设备','状态'],['主机','已验收']]}}}]));
 assert.ok(withHeaderRow.points[0].details[0].includes('主机；已验收'));
});
test('bounded reads and omitted details never imply full-document coverage',()=>{
 const result=summarizeDocument(data(Array.from({length:110},(_,i)=>p('第'+i+'段内容')),250));
 assert.equal(result.partial,true); assert.equal(result.covered,100); assert.equal(result.points.length,8); assert.equal(result.omitted,true);
 const long=summarizeDocument(data([p('长'.repeat(5000))])); assert.equal(long.partial,true); assert.ok(long.points[0].details[0].length<=141);
});
test('empty and image-only documents do not receive invented summaries or missing-field cards',()=>{
 assert.equal(summarizeDocument(data([])).points.length,0);
 assert.equal(summarizeDocument(data([{type:'image',text:''}])).points.length,0);
});
test('source strings including unsafe markup stay literal and extraction never mutates input',()=>{
 const input=data([p('<script>alert(1)</script>'),h('**处理事项**'),p('重要：保留原件。')]);
 const original=JSON.stringify(input); const result=summarizeDocument(input);
 assert.equal(JSON.stringify(input),original); assert.equal(result.points[0].details[0],'<script>alert(1)</script>');
 assert.equal(result.points[1].details[0],'重要：保留原件。');
});
