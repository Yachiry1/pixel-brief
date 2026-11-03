import json
from dataclasses import replace
from io import BytesIO

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient
from groq import AsyncGroq
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import config, documents, main, summarizer

ENGLISH = 'City parks reduce urban heat. Trees provide shade and absorb rainfall. Parks also support physical activity and mental health. Access should be equitable.'
UKRAINIAN = 'Міські парки зменшують спеку. Дерева створюють тінь і поглинають дощову воду. Парки сприяють фізичній активності та покращують психічне здоров’я. Доступ має бути рівним.'


@pytest.fixture
def client(monkeypatch):
    settings = replace(config.settings, api_key='server-test-key')
    for module in (main, documents, summarizer):
        monkeypatch.setattr(module, 'settings', settings)
    with TestClient(main.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def upstream(monkeypatch):
    state = {'requests': [], 'status': 200, 'summary': 'Parks cool cities and support well-being. Trees reduce flood risk. Equitable access matters.', 'finish': 'stop'}

    def handle(request):
        state['requests'].append(request)
        if state['status'] != 200:
            return httpx.Response(state['status'], json={'error': {'message': 'PRIVATE PROVIDER DETAIL', 'type': 'api_error'}})
        return httpx.Response(200, json={
            'id': 'test-completion', 'object': 'chat.completion', 'created': 1, 'model': 'openai/gpt-oss-20b',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': state['summary']}, 'finish_reason': state['finish']}],
        })

    def create_client(**kwargs):
        assert kwargs['max_retries'] == 0
        return AsyncGroq(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr(summarizer, 'AsyncGroq', create_client)
    return state


def pdf_bytes(text=None, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('password')
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def docx_bytes():
    document = Document()
    document.add_paragraph('Trees reduce heat.')
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = 'Parks'
    table.cell(0, 1).text = 'Support health'
    document.add_paragraph('Access should be equitable.')
    output = BytesIO()
    document.save(output)
    return output.getvalue()


@pytest.mark.parametrize('text', [ENGLISH, UKRAINIAN])
@pytest.mark.parametrize('length,expected', [('short', '1–2'), ('standard', '3–4')])
def test_language_and_length_one_real_sdk_request(client, upstream, text, length, expected):
    summaries = {
        'short': ('Міські парки зменшують спеку та підтримують здоров’я. Доступ до них має бути рівним.' if text == UKRAINIAN else 'City parks reduce heat and support health. Access should be equitable.'),
        'standard': UKRAINIAN if text == UKRAINIAN else ENGLISH,
    }
    upstream['summary'] = '  ' + summaries[length] + '\n'
    response = client.post('/api/summarize', data={'text': text, 'length': length})
    assert response.status_code == 200
    assert response.json()['summary'] == upstream['summary'].strip()
    assert len(upstream['requests']) == 1
    payload = json.loads(upstream['requests'][0].content)
    assert payload['messages'][1]['content'] == text
    assert expected in payload['messages'][0]['content']
    prompt = payload['messages'][0]['content']
    assert 'untrusted source data' in prompt
    assert f'HARD MAXIMUM: {2 if length == "short" else 4} sentences' in prompt
    assert 'omit lower-priority details rather than adding sentences' in prompt
    assert 'silently check the sentence count' in prompt
    assert payload['include_reasoning'] is False
    assert payload['temperature'] == 0.2
    assert 'tools' not in payload


@pytest.mark.parametrize('filename,content,expected', [
    ('test.txt', ENGLISH.encode(), ENGLISH),
    ('test.md', UKRAINIAN.encode(), UKRAINIAN),
    ('test.TXT', UKRAINIAN.encode('utf-16'), UKRAINIAN),
    ('test.txt', ENGLISH.encode('utf-32'), ENGLISH),
    ('test.pdf', pdf_bytes('Parks cool cities.'), 'Parks cool cities.'),
    ('test.docx', docx_bytes(), 'Trees reduce heat.\nParks\tSupport health\nAccess should be equitable.'),
])
def test_uploads(client, upstream, filename, content, expected):
    response = client.post('/api/summarize', data={'length': 'short'}, files={'file': (filename, content)})
    assert response.status_code == 200, response.text
    assert len(upstream['requests']) == 1
    assert json.loads(upstream['requests'][0].content)['messages'][1]['content'] == expected


@pytest.mark.parametrize('data', [{}, {'text': '  '}, {'text': '...'}, {'text': ENGLISH, 'length': 'long'}, {'text': 'x' * 20001}, {'text': 'я' * 13000}])
def test_invalid_text_never_calls_llm(client, upstream, data):
    response = client.post('/api/summarize', data=data)
    assert response.status_code in (400, 413)
    assert response.json()['error']
    assert not upstream['requests']


@pytest.mark.parametrize('name,content,status', [
    ('test.exe', b'not a document', 400), ('test.txt', b'', 400),
    ('test.txt', b'\x81\x82\xff', 400), ('test.txt', b'a\x00b', 400),
    ('test.pdf', b'broken', 400), ('test.docx', b'broken', 400),
    ('test.pdf', pdf_bytes(), 400), ('test.pdf', pdf_bytes('secret', True), 400),
    ('test.txt', b'x' * (5242880 + 1), 413),
    ('test.txt', b'x' * (5242880 + 100000), 413),
])
def test_invalid_files_never_call_llm(client, upstream, name, content, status):
    response = client.post('/api/summarize', files={'file': (name, content)})
    assert response.status_code == status, response.text
    assert not upstream['requests']


def test_conflicting_sources(client, upstream):
    response = client.post('/api/summarize', data={'text': ENGLISH}, files={'file': ('test.txt', ENGLISH.encode())})
    assert response.status_code == 400
    assert not upstream['requests']


def test_key_precedence(client, upstream):
    response = client.post('/api/summarize', data={'text': ENGLISH, 'api_key': 'user-test-key'})
    assert response.status_code == 200
    assert upstream['requests'][0].headers['authorization'] == 'Bearer user-test-key'
    assert 'user-test-key' not in response.text


def test_missing_key(client, upstream, monkeypatch):
    monkeypatch.setattr(main, 'settings', replace(main.settings, api_key=''))
    assert client.post('/api/summarize', data={'text': ENGLISH}).status_code == 401
    assert not upstream['requests']


@pytest.mark.parametrize('status,expected', [(401, 401), (429, 429), (403, 502), (400, 502), (500, 502)])
def test_provider_errors_no_retry(client, upstream, status, expected):
    upstream['status'] = status
    response = client.post('/api/summarize', data={'text': ENGLISH})
    assert response.status_code == expected
    assert len(upstream['requests']) == 1
    assert 'PRIVATE PROVIDER DETAIL' not in response.text
    assert 'server-test-key' not in response.text


@pytest.mark.parametrize('exception,status', [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)])
def test_network_errors_no_retry(client, monkeypatch, exception, status):
    calls = []

    def handle(request):
        calls.append(request)
        raise exception('private detail', request=request)

    def create_client(**kwargs):
        return AsyncGroq(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr(summarizer, 'AsyncGroq', create_client)
    response = client.post('/api/summarize', data={'text': ENGLISH})
    assert response.status_code == status
    assert len(calls) == 1


@pytest.mark.parametrize('summary,finish', [('', 'stop'), ('   ', 'stop'), ('Partial summary', 'length')])
def test_incomplete_result(client, upstream, summary, finish):
    upstream.update(summary=summary, finish=finish)
    assert client.post('/api/summarize', data={'text': ENGLISH}).status_code == 502
    assert len(upstream['requests']) == 1


def test_health_and_frontend(client):
    health = client.get('/api/health')
    assert health.json()['status'] == 'online'
    assert 'server-test-key' not in health.text
    assert health.headers['cache-control'] == 'no-store'
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/.env').status_code == 404
