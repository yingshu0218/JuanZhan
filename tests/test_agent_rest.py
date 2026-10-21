import pytest
from test_parsing import pipeline
from test_agents import credential,parsed
from test_converter import real_server
from juanzhan.agent_rest import Client,ClientError

def test_vendor_neutral_rest_client_actual_evidence_and_revoke(pipeline):
    settings,admin,csrf,space=pipeline
    document=parsed(pipeline)
    token,_=credential(pipeline)
    with real_server(admin.app) as base:
        client=Client(base+'/api/v1/agent',token['token'])
        assert client.call('list_spaces')['items'][0]['id']==space
        assert set(client.call('get_catalog',{'space_id':space}))=={'folders','tags','document_types','fields'}
        result=client.call('search_documents',{'space_id':space,'text':'合同'})
        assert result['items'][0]['id']==document
        overview=client.call('get_document_overview',{'space_id':space,'document_id':document})
        content=client.call('read_document',{'space_id':space,'document_id':document,'parse_run_id':overview['parse_run_id']})
        assert content['blocks']
        context=client.call('prepare_analysis',{'space_id':space,'document_ids':[document],'question':'合同金额与风险是什么？'})
        assert context['answer_generated'] is False
        with pytest.raises(ClientError):client.call('delete_document',{'document_id':document})
        admin.delete('/api/v1/agent-tokens/'+token['id'],headers=csrf)
        with pytest.raises(ClientError,match='401'):client.call('list_spaces')

@pytest.mark.parametrize('url',['http://example.test/api/v1/agent','https://user:pass@example.test/api/v1/agent','https://example.test/api/v1/agent?token=secret','https://example.test/api/v1/spaces','file:///tmp/api/v1/agent'])
def test_client_rejects_unsafe_or_wrong_resource(url):
    with pytest.raises(ClientError):Client(url,'jza_test')
