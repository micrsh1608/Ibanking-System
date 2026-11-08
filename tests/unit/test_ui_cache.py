import re

import pytest
from fastapi.testclient import TestClient

from services.account.main import app


@pytest.mark.parametrize('path',['/ui/','/ui/index.html','/ui/account-forms.js'])
def test_ui_never_uses_cached_or_conditional_not_modified_responses(path):
    with TestClient(app) as client:
        first=client.get(path)
        assert first.status_code==200 and 'no-store' in first.headers['cache-control']
        headers={'If-Modified-Since':'Wed, 01 Jan 2099 00:00:00 GMT'}
        if first.headers.get('etag'):headers['If-None-Match']=first.headers['etag']
        fresh=client.get(path,headers=headers)
        assert fresh.status_code==200 and fresh.content==first.content
        assert fresh.headers['pragma']=='no-cache'


def test_html_assets_share_a_revision_and_include_email_verification_entry():
    with TestClient(app) as client:
        response=client.get('/ui/?v=reload-email-proof')
        revision=response.headers['x-ui-version']
        links=re.findall(r'(?:src|href)="(\./[^"?]+\.(?:js|css))\?v=([a-f0-9]+)"',response.text)
        assert len(links)==7 and {value for _,value in links}=={revision}
        assert 'id="emailVerificationCode"' in response.text
        assert response.text.index('id="emailVerificationPanel"')<response.text.index('id="profileForm"')


@pytest.mark.parametrize('path',['/users/me','/accounts/me'])
def test_private_user_responses_cannot_be_cached(stack,path):
    response=stack.account.get(path,headers=stack.headers)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
