document.addEventListener('DOMContentLoaded', () => {
  const socket = io();

  // DOM elements
  const topicInput = document.getElementById('topic-input');
  const startResearchBtn = document.getElementById('start-research-btn');
  const errorMessage = document.getElementById('error-message');
  const statusMessage = document.getElementById('status-message');
  const subtopicListContainer = document.getElementById('subtopic-list-container');
  const reportContainer = document.getElementById('report-container');

  let currentTopic = '';

  // SVG icons
  const icons = {
    loader: `<svg class="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`,
    check: `<svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" /></svg>`,
    error: `<svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" /></svg>`,
    dot: `<svg class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><circle cx="10" cy="10" r="8" /></svg>`,
    airplane: `<svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" /></svg>`
  };

  // UI State
  const setUIState = (isResearching) => {
    topicInput.disabled = isResearching;
    startResearchBtn.disabled = isResearching || !topicInput.value.trim();
    startResearchBtn.classList.toggle('cursor-wait', isResearching);

    if (isResearching) {
      startResearchBtn.innerHTML = `${icons.loader}<span>Researching...</span>`;
    } else {
      startResearchBtn.innerHTML = `${icons.airplane}<span>Start Research</span>`;
    }
  };

  const resetUI = () => {
    errorMessage.textContent = '';
    subtopicListContainer.innerHTML = '';
    reportContainer.innerHTML = '';
    reportContainer.style.display = 'none';
    statusMessage.textContent = 'Ready to start your research.';
    setUIState(false);
  };

  setUIState(false);
  topicInput.addEventListener('input', () => setUIState(false));

  // WebSocket Events
  socket.on('connect', () => console.log('Connected to server!'));

  const setStatusColor = (cls) => {
    const dot = document.querySelector('#status-message span');
    if (dot) dot.className = `inline-block h-2 w-2 rounded-full ${cls}`;
  };

  socket.on('status_update', (data) => {
    statusMessage.textContent = data.message;
  });

  socket.on('sub_topics_generated', (data) => {
    setStatusColor('bg-sky-500');
    renderSubTopicList(data.sub_topics);
  });

  socket.on('sub_topic_update', (data) => {
    updateSubTopicStatus(data.index, data.status);
  });

  socket.on('final_report', (data) => {
    renderReport(data.report);
    setStatusColor('bg-emerald-500');
    setUIState(false);
  });

  socket.on('research_error', (data) => {
    errorMessage.textContent = data.error;
    statusMessage.textContent = 'An error occurred.';
    setStatusColor('bg-rose-500');
    setUIState(false);
  });

  // Render functions
  const renderSubTopicList = (subTopics) => {
    const html = `
      <div class="mt-8 border-t border-gray-200 dark:border-zinc-700 pt-6">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Research Plan</h3>
        <ul id="subtopics-ul" class="mt-4 space-y-3">
          ${subTopics.map(subTopic => `
            <li class="flex items-center justify-between p-3 bg-white dark:bg-zinc-800 rounded-lg border-l-4 border-gray-300 dark:border-zinc-600">
              <span class="text-sm text-gray-800 dark:text-gray-300">${subTopic.topic}</span>
              <div class="flex items-center gap-2 text-sm font-medium text-gray-500 dark:text-gray-400">
                ${icons.dot}
                <span class="capitalize">pending</span>
              </div>
            </li>
          `).join('')}
        </ul>
      </div>
    `;
    subtopicListContainer.innerHTML = html;
  };

  const updateSubTopicStatus = (index, status) => {
    const ul = document.getElementById('subtopics-ul');
    if (!ul || !ul.children[index]) return;

    const listItem = ul.children[index];
    const statusDiv = listItem.querySelector('div');

    const statusInfo = {
      'pending': { icon: icons.dot, text: 'pending', color: 'text-gray-500 dark:text-gray-400', border: 'border-gray-300 dark:border-zinc-600' },
      'in-progress': { icon: icons.loader, text: 'in progress', color: 'text-sky-500 dark:text-sky-400', border: 'border-sky-500' },
      'complete': { icon: icons.check, text: 'complete', color: 'text-emerald-500 dark:text-emerald-400', border: 'border-emerald-500' },
      'error': { icon: icons.error, text: 'error', color: 'text-rose-500 dark:text-rose-400', border: 'border-rose-500' }
    };

    const currentStatus = statusInfo[status];
    if (currentStatus) {
      listItem.className = `flex items-center justify-between p-3 bg-white dark:bg-zinc-800 rounded-lg border-l-4 ${currentStatus.border}`;
      statusDiv.className = `flex items-center gap-2 text-sm font-medium ${currentStatus.color}`;
      statusDiv.innerHTML = `${currentStatus.icon}<span class="capitalize">${currentStatus.text}</span>`;
    }
  };

  const renderReport = (report) => {
    let html = report
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900 dark:text-gray-100">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>');

    html = html.split('\n\n').map(block => {
      if (block.startsWith('### ')) return `<h3 class="text-xl font-bold mb-2 mt-4 text-gray-100">${block.substring(4)}</h3>`;
      if (block.startsWith('## ')) return `<h2 class="text-2xl font-bold mb-3 mt-5 text-white border-b border-zinc-700 pb-2">${block.substring(3)}</h2>`;
      if (block.startsWith('# ')) return `<h1 class="text-3xl font-bold mb-4 mt-6 text-white">${block.substring(2)}</h1>`;
      if (block.match(/^- /)) {
        const items = block.split('\n').map(item => `<li class="mb-1">${item.substring(2)}</li>`).join('');
        return `<ul class="list-disc pl-6 space-y-1 my-4">${items}</ul>`;
      }
      return `<p class="mb-4 text-gray-300 leading-relaxed">${block}</p>`;
    }).join('');

    const reportHTML = `
      <h2 class="text-3xl font-extrabold text-white">Final Report: <span class="text-sky-400">${currentTopic}</span></h2>
      <div class="mt-6 p-6 sm:p-8 bg-zinc-900/80 rounded-xl shadow-2xl border border-zinc-800 backdrop-blur-sm">
        ${html}
      </div>
    `;
    reportContainer.innerHTML = reportHTML;
    reportContainer.style.display = 'block';
  };

  // Start research
  const startResearch = () => {
    const topic = topicInput.value;
    if (!topic.trim()) {
      errorMessage.textContent = 'Please enter a research topic.';
      return;
    }

    currentTopic = topic;
    resetUI();
    setUIState(true);
    socket.emit('start_research', { topic });
  };

  startResearchBtn.addEventListener('click', startResearch);
  topicInput.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') startResearch();
  });
});
