document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const removeFile = document.getElementById('removeFile');
    const convertBtn = document.getElementById('convertBtn');
    const convertProgress = document.getElementById('convertProgress');
    const convertProgressFill = document.getElementById('convertProgressFill');
    const convertProgressText = document.getElementById('convertProgressText');
    const convertResult = document.getElementById('convertResult');
    const downloadBtn = document.getElementById('downloadBtn');
    const previewBtn = document.getElementById('previewBtn');

    let currentFile = null;

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFile(e.target.files[0]);
    });

    function handleFile(file) {
        if (!file.name.endsWith('.zip')) {
            alert('Пожалуйста, выберите ZIP-архив');
            return;
        }
        currentFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = (file.size / 1024).toFixed(1) + ' KB';
        fileInfo.classList.remove('hidden');
        dropZone.classList.add('hidden');
        convertBtn.disabled = false;
    }

    removeFile.addEventListener('click', () => {
        currentFile = null;
        fileInfo.classList.add('hidden');
        dropZone.classList.remove('hidden');
        convertBtn.disabled = true;
        fileInput.value = '';
    });

    convertBtn.addEventListener('click', () => {
        if (!currentFile) return;
        convertBtn.disabled = true;
        convertProgress.classList.remove('hidden');
        convertResult.classList.add('hidden');

        const formData = new FormData();
        formData.append('file', currentFile);
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 50);
                convertProgressFill.style.width = percent + '%';
                convertProgressText.textContent = `Загрузка ${percent}%`;
            }
        });

        xhr.addEventListener('load', () => {
            if (xhr.status === 200) {
                try {
                    const result = JSON.parse(xhr.responseText);
                    convertProgressFill.style.width = '100%';
                    convertProgressText.textContent = 'Готово!';
                    convertResult.classList.remove('hidden');
                    downloadBtn.href = result.download_url;
                    previewBtn.href = result.preview_url || '#';
                    setTimeout(() => convertProgress.classList.add('hidden'), 1000);
                } catch (e) {
                    alert('Неверный ответ сервера');
                    convertBtn.disabled = false;
                }
            } else {
                alert('Ошибка сервера: ' + xhr.status);
                convertBtn.disabled = false;
            }
        });

        xhr.addEventListener('error', () => {
            alert('Ошибка сети');
            convertBtn.disabled = false;
        });

        xhr.open('POST', '/api/convert');
        xhr.send(formData);
    });
});