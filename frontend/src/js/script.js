document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element Selection ---
    const generatorSelect = document.getElementById('generator-select');
    const fileInput = document.getElementById('file-input');
    const uploadForm = document.getElementById('upload-form');
    const statusDiv = document.getElementById('status');
    const resultDiv = document.getElementById('result');
    const progressBar = document.getElementById('progress-bar');

    let pollingInterval;

    // --- Core Functions ---

    /**
     * Fetches all available generators from the backend and populates the dropdown.
     */
    async function fetchAndPopulateGenerators() {
        try {
            const response = await fetch('/api/generators');
            if (!response.ok) {
                throw new Error('Failed to fetch generator options.');
            }
            const generators = await response.json();

            generatorSelect.innerHTML = '<option selected disabled>Choose a generator...</option>';

            // Dynamically create option groups for each generator type
            for (const type in generators) {
                const optgroup = document.createElement('optgroup');
                optgroup.label = type.charAt(0).toUpperCase() + type.slice(1); // Capitalize type name

                generators[type].forEach(option => {
                    const opt = document.createElement('option');
                    // Store both type and name in the option's value for easy access
                    opt.value = JSON.stringify({ type: type, name: option.value });
                    opt.textContent = option.text;
                    optgroup.appendChild(opt);
                });
                generatorSelect.appendChild(optgroup);
            }
        } catch (error) {
            updateStatus(`Error: ${error.message}`, 'bg-danger');
        }
    }

    /**
     * Handles the form submission to start a generation job.
     */
    async function startGeneration(event) {
        event.preventDefault(); // Prevent default form submission

        const file = fileInput.files[0];
        if (!file || generatorSelect.value === '') {
            updateStatus('Please select a file and a generator.', 'bg-warning');
            return;
        }

        // Parse the selected generator info from the dropdown value
        const selectedGenerator = JSON.parse(generatorSelect.value);

        // Use FormData to send both the file and other parameters
        const formData = new FormData();
        formData.append('file', file);
        formData.append('original_filename', file.name);
        formData.append('generator_type', selectedGenerator.type);
        formData.append('generator_name', selectedGenerator.name);

        resetUI();
        updateStatus('Uploading file and starting job...', 'bg-info');

        try {
            // POST to the new generic '/api/generate' endpoint
            const response = await fetch('/api/generate', {
                method: 'POST',
                body: formData, // No 'Content-Type' header needed, browser sets it for FormData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to start job.');
            }

            const data = await response.json();
            pollStatus(data.task_id);

        } catch (error) {
            updateStatus(`Error: ${error.message}`, 'bg-danger');
        }
    }

    /**
     * Polls the backend for the status of a job.
     * @param {string} taskId The ID of the job to poll.
     */
    function pollStatus(taskId) {
        if (pollingInterval) clearInterval(pollingInterval);

        let progress = 0;
        updateStatus(`Job submitted (ID: ${taskId.substring(0, 8)}...). Waiting for worker...`, 'bg-info');

        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/status/${taskId}`);
                if (!response.ok) {
                     // Stop polling on server errors
                    throw new Error(`Server returned status: ${response.status}`);
                }
                const data = await response.json();

                // Update progress bar for visual feedback
                progress = Math.min(progress + 10, 90);
                updateProgressBar(progress);

                switch (data.state) {
                    case 'SUCCESS':
                        clearInterval(pollingInterval);
                        updateProgressBar(100);
                        updateStatus('Job Successful!', 'bg-success');
                        showResult(data.result);
                        break;
                    case 'FAILURE':
                        clearInterval(pollingInterval);
                        updateProgressBar(100, true);
                        updateStatus(`Error! ${data.error}`, 'bg-danger');
                        break;
                    case 'ACTIVE':
                         updateStatus('Job is running...', 'bg-info');
                         break;
                    case 'PENDING':
                         updateStatus('Job is pending in queue...', 'bg-secondary');
                         break;
                    case 'NOT_FOUND':
                        clearInterval(pollingInterval);
                        updateStatus(`Error! Job ID ${taskId} not found. It may have expired.`, 'bg-danger');
                        break;
                    default:
                        // Continue polling
                }
            } catch (error) {
                clearInterval(pollingInterval);
                updateStatus(`Error: ${error.message}`, 'bg-danger');
            }
        }, 5000);
    }


    // --- UI Helper Functions ---
    function resetUI() {
        statusDiv.style.display = 'none';
        resultDiv.style.display = 'none';
        resultDiv.innerHTML = '';
        progressBar.parentElement.style.display = 'none';
        updateProgressBar(0);
    }

    function updateStatus(message, bgClass) {
        statusDiv.style.display = 'block';
        statusDiv.textContent = message;
        statusDiv.className = `alert ${bgClass} text-white`;
        if (bgClass !== 'bg-danger' && bgClass !== 'bg-success') {
            progressBar.parentElement.style.display = 'block';
        }
    }

    function updateProgressBar(percentage, isError = false) {
        progressBar.style.width = `${percentage}%`;
        progressBar.setAttribute('aria-valuenow', percentage);
        progressBar.classList.remove('bg-success', 'bg-danger');
        if (isError) {
             progressBar.classList.add('bg-danger');
        } else if (percentage === 100) {
             progressBar.classList.add('bg-success');
        }
    }

    function showResult(filename) {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <h5>Artifact Ready:</h5>
            <p>${filename}</p>
            <a href="/api/download/${filename}" class="btn btn-success" download>Download Artifact</a>
        `;
    }

    uploadForm.addEventListener('submit', startGeneration);
    fetchAndPopulateGenerators();
});
