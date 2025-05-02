document.addEventListener('DOMContentLoaded', function() {
    const checkboxes = document.querySelectorAll('.slide-checkbox');
    const thumbnailCards = document.querySelectorAll('.thumbnail-card');
    const selectAllBtn = document.getElementById('selectAll');
    const deselectAllBtn = document.getElementById('deselectAll');
    const selectedCountEl = document.getElementById('selectedCount');
    const generateBtn = document.getElementById('generateBtn');
    const setNameInput = document.getElementById('set_name');
    const namePreview = document.getElementById('name_preview');

    // Update selected count
    function updateSelectedCount() {
        const selectedCount = document.querySelectorAll('.slide-checkbox:checked').length;
        selectedCountEl.textContent = selectedCount;

        // Disable generate button if no slides selected
        if (selectedCount === 0) {
            generateBtn.disabled = true;
            generateBtn.innerHTML = '<i class="fas fa-exclamation-circle me-1"></i> Select at least one slide';
        } else {
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<i class="fas fa-file-pdf me-1"></i> Create PDF Set and Generate QR Code';
        }
    }

    // Make entire card clickable
    thumbnailCards.forEach(card => {
        card.addEventListener('click', function(e) {
            // Don't toggle if clicking directly on the checkbox (let the checkbox handle that)
            if (e.target.type !== 'checkbox') {
                const thumbnailId = this.dataset.thumbnailId;
                const checkbox = document.getElementById('thumb-' + thumbnailId);
                checkbox.checked = !checkbox.checked;

                // Update visual state
                if (checkbox.checked) {
                    this.classList.add('border-primary', 'border-2');
                } else {
                    this.classList.remove('border-primary', 'border-2');
                }

                updateSelectedCount();
            }
        });
    });

    // Add event listeners to checkboxes
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const card = this.closest('.thumbnail-card');
            if (this.checked) {
                card.classList.add('border-primary', 'border-2');
            } else {
                card.classList.remove('border-primary', 'border-2');
            }
            updateSelectedCount();
        });
    });

    // Select all button
    selectAllBtn.addEventListener('click', function() {
        checkboxes.forEach(checkbox => {
            checkbox.checked = true;
            const card = checkbox.closest('.thumbnail-card');
            card.classList.add('border-primary', 'border-2');
        });
        updateSelectedCount();
    });

    // Deselect all button
    deselectAllBtn.addEventListener('click', function() {
        checkboxes.forEach(checkbox => {
            checkbox.checked = false;
            const card = checkbox.closest('.thumbnail-card');
            card.classList.remove('border-primary', 'border-2');
        });
        updateSelectedCount();
    });

    // Set name validation and preview
    setNameInput.addEventListener('input', function() {
        // Replace spaces with underscores in real-time
        const sanitizedValue = this.value.replace(/\s+/g, '_').replace(/[^A-Za-z0-9_-]/g, '');

        // Only update if the value would change (prevents cursor jumping)
        if (this.value !== sanitizedValue) {
            this.value = sanitizedValue;
        }

        // Update preview
        namePreview.textContent = sanitizedValue || 'your_set_name';
    });

    // Form submission - show loading overlay and connect to WebSocket
    document.querySelector('form').addEventListener('submit', function(e) {
        // Show the loading overlay
        document.getElementById('loadingOverlay').classList.remove('d-none');

        // Don't connect to WebSocket if form is invalid
        if (!this.checkValidity()) {
            return;
        }

        // Get the PDF ID from the URL
        const pdfId = window.location.pathname.split('/').pop();

        // Get information about the selected slides
        const selectedSlides = document.querySelectorAll('.slide-checkbox:checked').length;
        const setName = document.getElementById('set_name').value;

        // Show file information and loading animation
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');
        const loadingMessage = document.getElementById('loadingMessage');

        // Display set name and slide count
        document.getElementById('setNameDisplay').textContent = setName;
        document.getElementById('slidesCountDisplay').textContent = selectedSlides;
        loadingMessage.textContent = `Creating PDF set: ${setName}`;
        progressText.textContent = `Processing ${selectedSlides} slides into a PDF`;

        // Add warning for large sets
        if (selectedSlides > 20) {
            const warningElement = document.createElement('div');
            warningElement.className = 'alert alert-warning';
            warningElement.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i> Please note, due to the size of the set, processing might take a bit longer than expected. But trust us, it\'s working.';
            document.getElementById('warningContainer').appendChild(warningElement);
        }

        // Animate the progress bar - slower but steady animation
        let progress = 0;
        const interval = setInterval(() => {
            // Slowly increase progress up to 95%
            if (progress < 95) {
                progress += 0.5;
                progressBar.style.width = `${progress}%`;
            }
        }, 500);
    });

    // Initial count update
    updateSelectedCount();

    // Initial name preview
    namePreview.textContent = 'your_set_name';
});
