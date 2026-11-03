'use strict';
const $ = (id) => document.getElementById(id);
const form = $('summary-form');
const source = $('source-text');
const output = $('output-panel');
let mode = 'text';
let selectedFile = null;
let processing = false;
let copyTimer;
let limits = {
  max_input_chars: 20000,
  max_input_bytes: 24000,
  max_file_bytes: 5242880
};
source.placeholder = 'Drop your thoughts here.\n\nPaste an article, lecture notes, a research paper, or anything that could use a little less… everything.';

// Original pixel illustration, generated locally without images or AI requests.
const svgNS = 'http://www.w3.org/2000/svg';
const globe = $('globe-pixels');
const continents = [
  [
    [-.86, -.48],
    [-.52, -.73],
    [-.19, -.62],
    [-.11, -.38],
    [-.37, -.16],
    [-.36, .08],
    [-.59, -.03],
    [-.66, -.21]
  ],
  [
    [-.38, .04],
    [-.08, .16],
    [.02, .4],
    [-.12, .74],
    [-.26, .88],
    [-.34, .57],
    [-.48, .27]
  ],
  [
    [.06, -.59],
    [.29, -.75],
    [.67, -.59],
    [.87, -.28],
    [.58, -.08],
    [.34, -.2],
    [.12, -.06],
    [-.03, -.27]
  ],
  [
    [.1, -.14],
    [.42, -.03],
    [.46, .28],
    [.26, .59],
    [.09, .37],
    [-.01, .11]
  ],
  [
    [.53, .47],
    [.77, .42],
    [.88, .63],
    [.59, .72]
  ],
];

function inside(x, y, polygon) {
  let yes = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i], [xj, yj] = polygon[j];
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) yes = !yes;
  }
  return yes;
}
for (let row = -17; row <= 17; row++) {
  for (let col = -17; col <= 17; col++) {
    const x = col / 17,
      y = row / 17,
      r = x * x + y * y;
    if (r > 1) continue;
    const land = continents.some(p => inside(x, y, p));
    const noise = ((col * 73 + row * 137 + 4999) % 19 + 19) % 19;
    if (!land && noise % 3 === 0 && r < .92) continue;
    const pixel = document.createElementNS(svgNS, 'rect');
    pixel.setAttribute('x', 218 + col * 6);
    pixel.setAttribute('y', 148 + row * 6);
    pixel.setAttribute('width', 4.7);
    pixel.setAttribute('height', 4.7);
    const lit = 1 - (x + .7) ** 2 / 5 - (y + .7) ** 2 / 7;
    pixel.setAttribute('fill', land ? (noise < 4 ? '#d0ffab' : lit > .55 ? '#b6ee87' : '#739e52') : (r > .88 ? '#7ca858' : lit > .7 ? '#3d602a' : '#273d20'));
    globe.appendChild(pixel);
  }
}

function updateCount() {
  const count = Array.from(source.value).length;
  $('input-count').textContent = `${count.toLocaleString()} / ${limits.max_input_chars.toLocaleString()} chars`;
  $('input-count').style.color = count > limits.max_input_chars ? '#ffbc9b' : '';
}

function switchMode(next) {
  if (processing) return;
  mode = next;
  for (const name of ['text', 'file']) {
    const tab = $(name + '-tab');
    const active = name === mode;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    $(name + '-mode').hidden = !active;
  }
}
for (const name of ['text', 'file']) {
  $(name + '-tab').addEventListener('click', () => switchMode(name));
  $(name + '-tab').addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const next = event.key === 'Home' ? 'text' : event.key === 'End' ? 'file' : mode === 'text' ? 'file' : 'text';
      switchMode(next);
      $(next + '-tab').focus();
    }
  });
}

function setState(state, message = '') {
  output.dataset.state = state;
  output.setAttribute('aria-busy', String(state === 'loading'));
  $('empty-state').hidden = state === 'success' || state === 'error';
  $('summary-result').hidden = state !== 'success';
  $('error-state').hidden = state !== 'error';
  $('copy-button').disabled = state !== 'success';
  const badge = {
    empty: 'STANDING BY',
    loading: 'PROCESSING',
    success: 'COMPLETE',
    error: 'ATTENTION'
  };
  const status = {
    empty: 'AWAITING INPUT',
    loading: 'PROCESSING...',
    success: 'SUMMARY READY',
    error: 'ACTION REQUIRED'
  };
  $('output-badge').textContent = badge[state];
  $('output-status').replaceChildren(Object.assign(document.createElement('i'), {}), document.createTextNode(' ' + status[state]));
  $('output-meta').textContent = state === 'empty' ? 'READY WHEN YOU ARE' : state === 'loading' ? 'DISTILLING THE ESSENTIALS' : state === 'error' ? 'CHECK YOUR INPUT' : '';
  if (state === 'loading') {
    $('state-title').textContent = 'PROCESSING...';
    $('state-description').textContent = 'Finding the signal in your source. Hang tight.';
    $('empty-hint').textContent = '[ A LITTLE LESS TEXT IS ON ITS WAY ]';
  } else if (state === 'empty') {
    $('state-title').textContent = 'AWAITING INPUT_';
    $('state-description').textContent = 'Big ideas go in. A little clarity comes out. Add your text and let’s get to the point.';
    $('empty-hint').textContent = '[ YOUR NEXT AHA MOMENT LIVES HERE ]';
  }
  if (state === 'error') $('error-message').textContent = message;
}

function showError(message) {
  setState('error', message);
}

function chooseFile(file) {
  if (processing || !file) return;
  if (!/\.(txt|md|pdf|docx)$/i.test(file.name)) {
    showError('Unsupported file type. Choose a TXT, MD, PDF, or DOCX file.');
    return;
  }
  if (file.size > limits.max_file_bytes) {
    showError(`This file is too large. Maximum size is ${(limits.max_file_bytes/1048576).toLocaleString()} MB.`);
    return;
  }
  if (file.size === 0) {
    showError('This file is empty. Choose a document containing text.');
    return;
  }
  selectedFile = file;
  $('file-label').textContent = file.name;
  $('file-description').textContent = 'Document selected. Ready to distill.';
  $('file-info').textContent = `${(file.size/1024).toFixed(1)} KB · ${file.name.split('.').pop().toUpperCase()}`;
  $('remove-file').hidden = false;
}
$('document-file').addEventListener('change', event => {
  chooseFile(event.target.files[0]);
  event.target.value = '';
});
$('remove-file').addEventListener('click', () => {
  selectedFile = null;
  $('file-label').textContent = 'Drop a document here';
  $('file-description').textContent = 'or click to browse your files';
  $('file-info').textContent = 'No document selected';
  $('remove-file').hidden = true;
});
let dragDepth = 0;
for (const eventName of ['dragenter', 'dragover', 'dragleave', 'drop']) {
  $('dropzone').addEventListener(eventName, event => {
    event.preventDefault();
    event.stopPropagation();
    if (processing) return;
    if (eventName === 'dragenter') dragDepth++;
    if (eventName === 'dragleave') dragDepth = Math.max(0, dragDepth - 1);
    if (eventName === 'drop') {
      dragDepth = 0;
      if (event.dataTransfer.files.length !== 1) showError('Please upload one document at a time.');
      else chooseFile(event.dataTransfer.files[0]);
    }
    $('dropzone').classList.toggle('dragover', eventName === 'dragover' || dragDepth > 0);
  });
}
source.addEventListener('input', updateCount);
$('clear-input').addEventListener('click', () => {
  source.value = '';
  updateCount();
  source.focus();
});
$('sample-button').addEventListener('click', () => {
  source.value = 'Urban green spaces play an important role in making cities healthier and more resilient. Trees and parks help reduce temperatures during heat waves by providing shade and releasing water vapor. They also absorb rainfall, which reduces the risk of flooding when drainage systems are overwhelmed. Access to green spaces is associated with improved mental well-being, more physical activity, and stronger social connections. However, these benefits are not distributed equally: low-income neighborhoods often have fewer trees and smaller parks. City planners can address this gap by prioritizing new green spaces in underserved areas and involving local residents in their design. Long-term maintenance and accessible public transport are essential to ensure these investments benefit the whole community.';
  updateCount();
  source.focus();
});

function setProcessing(busy) {
  processing = busy;
  for (const control of form.querySelectorAll('input,textarea,button')) control.disabled = busy;
  $('copy-button').disabled = busy || output.dataset.state !== 'success';
  $('submit-label').textContent = busy ? 'PROCESSING...' : 'SUMMARIZE';
  $('submit-arrow').hidden = busy;
  $('button-loader').hidden = !busy;
}
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (processing) return;
  const text = source.value.trim();
  if (mode === 'text') {
    if (!text) {
      showError('Paste some text before summarizing. You can also try the example.');
      source.focus();
      return;
    }
    if (Array.from(text).length > limits.max_input_chars) {
      showError(`Your text exceeds the ${limits.max_input_chars.toLocaleString()}-character limit. Shorten it and try again.`);
      return;
    }
    if (new TextEncoder().encode(text).length > limits.max_input_bytes) {
      showError(`Your text exceeds the ${limits.max_input_bytes.toLocaleString()}-byte model input limit. Shorten it and try again.`);
      return;
    }
  } else if (!selectedFile) {
    showError('Choose a document before summarizing.');
    $('document-file').focus();
    return;
  }
  const data = new FormData();
  data.append('length', form.querySelector('input[name="length"]:checked').value);
  data.append('api_key', $('api-key').value.trim());
  if (mode === 'text') data.append('text', text);
  else data.append('file', selectedFile);
  clearTimeout(copyTimer);
  $('copy-label').textContent = 'Copy';
  setProcessing(true);
  setState('loading');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch('/api/summarize', {
      method: 'POST',
      body: data,
      signal: controller.signal
    });
    const result = await response.json().catch(() => ({
      error: 'The server returned an unreadable response. Please try again.'
    }));
    if (!response.ok) {
      if (response.status === 401) {
        $('api-settings').open = true;
        $('key-status').textContent = 'KEY REQUIRED';
      }
      throw new Error(result.error || 'Unable to summarize this input. Please try again.');
    }
    if (typeof result.summary !== 'string' || !result.summary.trim()) throw new Error('The server returned an empty summary. Please try again.');
    $('summary-result').textContent = result.summary;
    setState('success');
    $('result-label').textContent = 'The essentials. All in one place.';
    $('output-meta').textContent = `${result.summary.trim().split(/\s+/u).length} WORDS · ${result.length.toUpperCase()}`;
    if (window.matchMedia('(max-width: 760px)').matches) output.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
      block: 'start'
    });
  } catch (error) {
    const message = error.name === 'AbortError' ? 'This request took too long. Try again in a moment.' : error instanceof TypeError ? 'Unable to connect to the server. Check your connection and try again.' : error.message;
    showError(message);
  } finally {
    clearTimeout(timer);
    setProcessing(false);
  }
});
$('copy-button').addEventListener('click', async () => {
  const text = $('summary-result').textContent;
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
    else {
      const copyArea = document.createElement('textarea');
      copyArea.value = text;
      copyArea.className = 'sr-only';
      document.body.appendChild(copyArea);
      copyArea.select();
      const copied = document.execCommand('copy');
      copyArea.remove();
      if (!copied) throw new Error('Clipboard unavailable');
    }
    $('copy-label').textContent = 'Copied!';
    $('output-status').lastChild.textContent = ' COPIED TO CLIPBOARD';
    copyTimer = setTimeout(() => {
      $('copy-label').textContent = 'Copy';
      if (output.dataset.state === 'success') $('output-status').lastChild.textContent = ' SUMMARY READY';
    }, 2200);
  } catch {
    $('copy-label').textContent = 'Select text';
    $('summary-result').focus();
    const range = document.createRange();
    range.selectNodeContents($('summary-result'));
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    $('output-status').lastChild.textContent = ' PRESS CTRL/CMD+C TO COPY';
  }
});
async function checkHealth() {
  try {
    const response = await fetch('/api/health', {
      signal: AbortSignal.timeout(8000)
    });
    if (!response.ok) throw new Error();
    const health = await response.json();
    limits = health;
    updateCount();
    $('system-status').lastElementChild.textContent = 'SYSTEM ONLINE';
    $('key-status').textContent = health.server_key_configured ? 'SERVER KEY READY' : 'KEY REQUIRED';
    if (!health.server_key_configured) $('api-settings').open = true;
    $('input-limit').textContent = `One document. One AI request. Up to ${limits.max_input_chars.toLocaleString()} characters.`;
  } catch {
    $('system-status').lastElementChild.textContent = 'SERVER UNREACHABLE';
  }
}
checkHealth();
