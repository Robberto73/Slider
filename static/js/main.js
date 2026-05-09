// static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('generateForm');
    const statusPanel = document.getElementById('generationStatus');
    const progressFill = document.getElementById('progressFill');
    const statusText = document.getElementById('statusText');
    const statusActions = document.getElementById('statusActions');
    const downloadLink = document.getElementById('downloadLink');

    // Валидация количества слайдов
    const slidesInput = document.querySelector('[name="slides_count"]');
    slidesInput.addEventListener('input', () => {
        let val = parseInt(slidesInput.value, 10);
        if (isNaN(val) || val < 1) slidesInput.value = 1;
        if (val > 30) slidesInput.value = 30;
    });

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
            model_type: formData.get('model_type')
        };

        statusPanel.classList.remove('hidden');
        statusActions.classList.add('hidden');
        progressFill.style.width = '0%';
        progressFill.style.background = 'var(--accent)';
        statusText.textContent = 'Отправка запроса...';

        try {
            const resp = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await resp.json();
            if (result.status === 'accepted') {
                pollStatus(result.project_id);
            } else {
                statusText.textContent = 'Ошибка: ' + (result.message || '');
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
                const data = await resp.json();

                progressFill.style.width = data.progress + '%';
                statusText.textContent = data.message || 'Генерация...';

                if (data.status === 'completed') {
                    clearInterval(interval);
                    progressFill.style.width = '100%';
                    statusText.textContent = '✅ Готово!';
                    statusActions.classList.remove('hidden');
                    downloadLink.href = data.download_url;
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    statusText.textContent = '❌ Ошибка: ' + data.message;
                    progressFill.style.background = '#C62828';
                }
            } catch (e) {
                console.error('Polling error:', e);
            }
        }, 1000);
    }
});