"""Real Chromium UI checks; summary network responses are deliberately mocked."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope='module')
def site():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=.3)
                break
            except OSError:
                time.sleep(.1)
        else:
            pytest.fail('Preview server did not start')
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as playwright:
        options = {'headless': True}
        executable = os.getenv('CHROMIUM_EXECUTABLE')
        if executable:
            options['executable_path'] = executable
        browser = playwright.chromium.launch(**options)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, site):
    context = browser.new_context(viewport={'width': 1440, 'height': 1100}, permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    page.goto(site)
    expect(page.locator('#system-status')).to_contain_text('SYSTEM ONLINE')
    yield page
    context.close()


def test_summary_copy_and_loading(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    summary = 'Urban parks cool cities. Trees absorb rainfall. Equitable access supports public health.'
    seen = []
    pending = []

    def respond(route):
        seen.append(route.request.post_data_buffer)
        pending.append(route)

    page.route('**/api/summarize', respond)
    page.locator('#sample-button').click()
    page.locator('#summarize-button').click()
    expect(page.locator('#summarize-button')).to_be_disabled()
    expect(page.locator('#submit-label')).to_have_text('PROCESSING...')
    page.evaluate('document.getElementById("summary-form").requestSubmit()')
    page.wait_for_timeout(100)
    assert len(pending) == 1
    pending[0].fulfill(json={'summary': summary, 'source_characters': 600, 'length': 'standard'})
    expect(page.locator('#summary-result')).to_have_text(summary)
    expect(page.locator('#summarize-button')).to_be_enabled()
    assert len(seen) == 1
    page.locator('#copy-button').click()
    expect(page.locator('#copy-label')).to_have_text('Copied!')
    assert page.evaluate('navigator.clipboard.readText()') == summary
    assert not errors


def test_validation_and_keyboard_tabs(page):
    page.locator('#summarize-button').click()
    expect(page.locator('#error-message')).to_contain_text('Paste some text')
    page.locator('#file-tab').focus()
    page.keyboard.press('ArrowRight')
    expect(page.locator('#file-tab')).to_have_attribute('aria-selected', 'true')
    page.keyboard.press('ArrowLeft')
    expect(page.locator('#text-tab')).to_have_attribute('aria-selected', 'true')
    page.locator('#file-tab').click()
    page.locator('#summarize-button').click()
    expect(page.locator('#error-message')).to_contain_text('Choose a document')
    page.locator('#document-file').set_input_files({'name': 'notes.exe', 'mimeType': 'application/octet-stream', 'buffer': b'bad'})
    expect(page.locator('#error-message')).to_contain_text('Unsupported file type')
    page.locator('#document-file').set_input_files({'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'Urban parks improve health.'})
    expect(page.locator('#file-label')).to_have_text('notes.txt')
    page.route('**/api/summarize', lambda route: route.fulfill(json={'summary': 'Urban parks improve health.', 'source_characters': 27, 'length': 'short'}))
    page.locator('input[value="short"]').check()
    page.locator('#summarize-button').click()
    expect(page.locator('#summary-result')).to_have_text('Urban parks improve health.')
    expect(page.locator('#output-meta')).to_contain_text('SHORT')
    page.locator('#remove-file').click()
    expect(page.locator('#file-info')).to_have_text('No document selected')


@pytest.mark.parametrize('status,message', [(401, 'Groq rejected the API key.'), (429, 'Rate limit reached. Wait a moment.')])
def test_friendly_errors(page, status, message):
    page.route('**/api/summarize', lambda route: route.fulfill(status=status, json={'error': message}))
    page.locator('#sample-button').click()
    page.locator('#summarize-button').click()
    expect(page.locator('#error-message')).to_have_text(message)
    expect(page.locator('#summarize-button')).to_be_enabled()
    expect(page.locator('#copy-button')).to_be_disabled()
    expect(page.locator('#source-text')).not_to_have_value('')
    if status == 401:
        expect(page.locator('#api-settings')).to_have_attribute('open', '')


@pytest.mark.parametrize('width', [360, 390, 768, 1024, 1440])
def test_responsive_layout_and_screenshots(page, width):
    page.set_viewport_size({'width': width, 'height': 1000})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    first = page.locator('.input-panel').bounding_box()
    second = page.locator('.output-panel').bounding_box()
    if width <= 760:
        assert second['y'] >= first['y'] + first['height']
    else:
        assert abs(first['y'] - second['y']) < 2
    page.locator('#file-tab').click()
    page.locator('#document-file').set_input_files({'name': 'very-long-document-name-' * 7 + '.txt', 'mimeType': 'text/plain', 'buffer': b'Trees help cities.'})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#text-tab').click()
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path=f'test-results/pixel-brief-{width}.png', full_page=True)
