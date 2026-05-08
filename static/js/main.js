document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('generateForm');
    const statusPanel = document.getElementById('generationStatus');
    const progressFill = document.getElementById('progressFill');
    const statusText = document.getElementById('statusText');
    const statusActions = document.getElementById('statusActions');
    const downloadLink = document.getElementById('downloadLink');

    // Быстрые шаблоны
    document.querySelectorAll('.template-card').forEach(card => {
        card.addEventListener('click', () => {
            const topic = card.dataset.topic;
            document.querySelector('[name="topic"]').value = topic;
            document.querySelectorAll('.template-card').forEach(c => c.style.borderColor = '');
            card.style.borderColor = 'var(--accent)';
        });
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const data = {
            topic: formData.get('topic'),
            slides_count: parseInt(formData.get('slides_count')),
            style: formData.get('style'),
            language: formData.get('language'),
            include_charts: formData.has('include_charts'),
            include_icons: formData.has('include_icons'),
            model_type: formData.get('model_type')   // <-- новое поле
        };

        statusPanel.classList.remove('hidden');
        statusActions.classList.add('hidden');
        progressFill.style.width = '10%';
        statusText.textContent = 'Отправка запроса агенту...';

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (result.status === 'completed') {
                progressFill.style.width = '100%';
                statusText.textContent = '✅ Генерация завершена!';
                statusActions.classList.remove('hidden');
                downloadLink.href = result.download_url;
            } else if (result.status === 'accepted') {
                // старая логика polling (если агент асинхронный)
                progressFill.style.width = '30%';
                statusText.textContent = 'Агент начал генерацию...';
                pollStatus(result.project_id);
            } else {
                statusText.textContent = 'Ошибка: ' + result.message;
                progressFill.style.width = '100%';
                progressFill.style.background = '#C62828';
            }
        } catch (err) {
            statusText.textContent = 'Ошибка сети: ' + err.message;
            progressFill.style.width = '100%';
            progressFill.style.background = '#C62828';
        }
    });

    async function pollStatus(projectId) {
        const interval = setInterval(async () => {
            try {
                const resp = await fetch(`/api/generate-status/${projectId}`);
                const status = await resp.json();
                progressFill.style.width = `${30 + status.progress * 0.7}%`;
                if (status.status === 'completed') {
                    clearInterval(interval);
                    progressFill.style.width = '100%';
                    statusText.textContent = '✅ Генерация завершена!';
                    statusActions.classList.remove('hidden');
                    downloadLink.href = status.download_url || `/api/download/${projectId}`;
                } else if (status.status === 'error') {
                    clearInterval(interval);
                    statusText.textContent = '❌ Ошибка генерации';
                    progressFill.style.background = '#C62828';
                } else {
                    statusText.textContent = `Генерация... ${status.progress}%`;
                }
            } catch (e) {
                console.error('Polling error:', e);
            }
        }, 2000);
    }
});