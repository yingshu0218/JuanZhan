"""Rules for the shared backend overview, independent of document type and UI."""
from copy import deepcopy
from juanzhan.overviews import summarize

def p(text):return {'type':'paragraph','text':text}
def h(text,level=1):return {'type':'heading','text':text,'structure':{'level':level}}
def data(items,total=None):return {'body':[{'id':'b'+str(i),'index':i,**item} for i,item in enumerate(items)],'total':len(items) if total is None else total}

def test_course_is_generic_points_not_fact_cards():
    result=summarize(data([p('摄影课程'),p('6节课 · 12小时 · 1980元'),h('课程内容'),h('曝光',2),p('掌握正确曝光。'),h('后期',2),h('安排'),p('周末直播。')]))
    assert 'facts' not in result and 'course' not in result
    assert '1980元' in result['points'][0]['details'][0]
    assert [point['label'] for point in result['points'][1:]]==['课程内容','安排']
    assert any(source['text']=='后期' for source in result['points'][1]['sources'])

def test_enclosing_title_and_subsections_are_retained():
    result=summarize(data([h('项目报告'),p('完成迁移。'),h('进展',2),p('已完成三个服务迁移。继续验收。'),h('风险',2),p('需数据抽查。')]))
    assert [point['label'] for point in result['points']]==['项目报告','进展','风险']
    assert result['points'][1]['details']==['已完成三个服务迁移。']

def test_plain_meeting_points_order_and_conditional_numbers():
    result=summarize(data([p('讨论接口调整。确认周五交付。'),{'type':'list_item','text':'王明负责测试。'},p('费用：1280-1980元/人，按班次收费')]))
    assert len(result['points'])==4
    assert result['points'][1]['details']==['确认周五交付。']
    assert result['points'][-1]['details']==['费用：1280-1980元/人，按班次收费']

def test_table_retains_columns_and_data_and_discloses_more_rows():
    result=summarize(data([h('清单'),{'type':'table','structure':{'table':{'headers':['设备','状态'],'rows':[['主机','已验收'],['路由器','待验证'],['交换机','未验收']]}}}]))
    assert '设备：主机；状态：已验收' in result['points'][0]['details'][0]
    assert result['omitted'] and result['points'][0]['sources'][1]['index']==1

def test_header_row_is_not_the_only_table_excerpt():
    result=summarize(data([h('清单'),{'type':'table','structure':{'table':{'rows':[['设备','状态'],['主机','已验收']]}}}]))
    assert '主机；已验收' in result['points'][0]['details'][0]

def test_long_content_and_document_scope_are_bounded():
    result=summarize(data([p('第'+str(i)+'段内容') for i in range(110)],250))
    assert result['partial'] and result['covered']==100 and len(result['points'])==8 and result['omitted']
    result=summarize(data([p('长'*5000)]));assert result['partial'] and len(result['points'][0]['details'][0])<=141

def test_empty_images_do_not_receive_fake_missing_field_cards():
    assert not summarize(data([]))['points']
    assert not summarize(data([{'type':'image','text':''}]))['points']

def test_untrusted_source_stays_literal_and_input_unchanged():
    original=data([p('<script>alert(1)</script>'),h('**重要事项**'),p('注意：保留原件。')]);before=deepcopy(original)
    result=summarize(original)
    assert original==before and result['points'][0]['details']==['<script>alert(1)</script>']
