document.addEventListener('DOMContentLoaded', function() {
    // File upload functionality
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    const fileInput = document.getElementById('pptx_file');
    const chooseFileButton = document.getElementById('chooseFileButton');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const uploadButton = document.getElementById('uploadButton');

    if (chooseFileButton && fileInput) {
        // Trigger file input click when "Choose file" button is clicked
        chooseFileButton.addEventListener('click', function() {
            fileInput.click();
        });

        // Update file name display when a file is selected
        fileInput.addEventListener('change', function() {
            if (fileInput.files && fileInput.files.length > 0) {
                const file = fileInput.files[0];
                const fileName = file.name;
                const fileSize = Math.round(file.size / (1024 * 1024)); // Size in MB
                
                // Get the user's premium status from the data attribute
                const premiumStatus = parseInt(document.body.getAttribute('data-premium-status') || '0');
                
                // Set size limits based on premium status
                let maxSizeMB = 20; // Default for free tier
                if (premiumStatus === 1) {
                    maxSizeMB = 30; // Premium tier
                } else if (premiumStatus === 2) {
                    maxSizeMB = 50; // Corporate tier
                }
                
                // Check if file size exceeds the limit
                if (fileSize > maxSizeMB) {
                    alert(`File size (${fileSize} MB) exceeds the maximum allowed for your plan (${maxSizeMB} MB). Please upgrade your plan or upload a smaller file.`);
                    // Reset the file input
                    fileInput.value = '';
                    fileNameDisplay.value = 'No file chosen';
                    return;
                }
                
                // Update the file name display
                fileNameDisplay.value = fileName;
                
                // Enable upload button if a file is selected and account is activated
                if (!uploadButton.disabled) { // Check if it's not disabled by account activation status
                    uploadButton.classList.remove('btn-secondary');
                    uploadButton.classList.add('btn-primary');
                    uploadButton.innerHTML = '<i class="fas fa-cloud-upload-alt me-1"></i> Upload';
                }
            } else {
                fileNameDisplay.value = 'No file chosen';
            }
        });

        // Handle initial state of upload button based on account activation
        if (uploadButton && uploadButton.disabled) {
            uploadButton.classList.remove('btn-primary');
            uploadButton.classList.add('btn-secondary');
            uploadButton.innerHTML = 'Please check your email to activate your account';
        }
    }

    // Upload progress tracking
    const uploadForm = document.getElementById('uploadForm');
    
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            // Get the file input
            const fileInput = document.getElementById('pptx_file');
            if (!fileInput.files || fileInput.files.length === 0) {
                return; // No file selected
            }
            
            // Get the user's premium status from the data attribute
            const premiumStatus = parseInt(document.body.getAttribute('data-premium-status') || '0');
            
            // Set size limits based on premium status
            let maxSizeMB = 20; // Default for free tier
            if (premiumStatus === 1) {
                maxSizeMB = 30; // Premium tier
            } else if (premiumStatus === 2) {
                maxSizeMB = 50; // Corporate tier
            }
            
            // Check file size again before submitting (double check)
            const file = fileInput.files[0];
            const fileSize = Math.round(file.size / (1024 * 1024)); // Size in MB
            
            if (fileSize > maxSizeMB) {
                e.preventDefault(); // Prevent form submission
                alert(`File size (${fileSize} MB) exceeds the maximum allowed for your plan (${maxSizeMB} MB). Please upgrade your plan or upload a smaller file.`);
                return;
            }
            
            // Show the loading overlay
            document.getElementById('uploadLoadingOverlay').classList.remove('d-none');
            
            // We'll create a unique ID for this upload based on timestamp
            const uploadId = Date.now().toString();
            
            // Get file information (in KB for display)
            const fileName = file.name;
            const fileSizeKB = Math.round(file.size / 1024); // Size in KB
            
            // Show file information and loading animation
            const progressBar = document.getElementById('uploadProgressBar');
            const progressText = document.getElementById('uploadProgressText');
            const loadingMessage = document.getElementById('uploadLoadingMessage');
            
            // Display presentation name and size
            document.getElementById('overlayFileNameDisplay').textContent = fileName;
            document.getElementById('fileSizeDisplay').textContent = `${fileSizeKB} KB`;
            loadingMessage.textContent = `Processing: ${fileName}`;
            
            // Add warning for large presentations
            if (fileSizeKB > 1000) { // Assuming larger files have more slides
                const warningElement = document.createElement('div');
                warningElement.className = 'alert alert-warning';
                warningElement.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i> Please note, due to the size of the file, processing might take a bit longer than expected. But trust us, it\'s working.';
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
    }

    // Function to handle QR code download via JavaScript
    async function downloadQrCode(button, url, filename) {
        try {
            // Show a simple loading indicator while maintaining button width
            const originalWidth = button.offsetWidth;
            button.style.width = originalWidth + 'px'; // Fix the width
            button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Downloading...';
            button.disabled = true;

            // Add cache-busting parameter to prevent browser caching
            const cacheBuster = `?cache=${Date.now()}`;
            const urlWithCacheBuster = url.includes('?') ? `${url}&cache=${Date.now()}` : `${url}${cacheBuster}`;

            const response = await fetch(urlWithCacheBuster, {
                headers: {
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! status: ${response.status}, detail: ${errorText}`);
            }

            const blob = await response.blob();

            // Create a link element and trigger the download
            const blobUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = blobUrl;
            a.download = filename; // Set desired filename
            document.body.appendChild(a);
            a.click();

            // Clean up
            window.URL.revokeObjectURL(blobUrl);
            a.remove();

        } catch (error) {
            console.error('Error downloading QR code:', error);
            alert('Failed to download QR code. Please try again.');
        } finally {
            // Restore button state
            // Need to determine the original button content based on class
            if (button.classList.contains('download-qr-btn')) {
                 button.innerHTML = '<i class="fas fa-qrcode me-1"></i> Download QR Code for PDF file';
            } else if (button.classList.contains('set-download-btn')) {
                 button.innerHTML = '<i class="fas fa-qrcode"></i>';
            }
            button.disabled = false;
            button.style.width = ''; // Remove fixed width
        }
    }


    // QR code download functionality for PDF presentations
    const downloadQrButtons = document.querySelectorAll('.download-qr-btn');
    if (downloadQrButtons.length > 0) {
        downloadQrButtons.forEach(button => {
            button.addEventListener('click', async function(e) {
                e.preventDefault(); // Prevent default link behavior

                const pdfId = this.dataset.pdfId;
                const filenameElement = this.closest('.card').querySelector('.card-header h3');
                let originalFilename = 'presentation'; // Default filename
                if (filenameElement) {
                    // Extract filename from the text content, removing "Presentation X/Y" and trimming
                    const textContent = filenameElement.textContent.trim();
                    const match = textContent.match(/Presentation \d+\/\d+\s*(.*)/);
                    if (match && match[1]) {
                         originalFilename = match[1].trim();
                    } else {
                         originalFilename = textContent; // Fallback if format changes
                    }
                }
                const baseFilename = originalFilename.replace(/\.[^/.]+$/, ""); // Remove extension
                const filename = `${baseFilename}_pdf_qr.png`; // Set desired filename

                // Increment the download count
                try {
                    fetch(`/increment-pdf-download/${pdfId}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                } catch (error) {
                    console.error('Error incrementing download count:', error);
                    // Continue with download even if tracking fails
                }

                // Use the generic download function with the URL from the href attribute
                const qrCodeUrl = this.href;
                if (qrCodeUrl && qrCodeUrl !== '#') {
                    await downloadQrCode(button, qrCodeUrl, filename);
                } else {
                    alert('QR code URL not available.');
                }
            });
        });
    }
    
    // Set download functionality and tracking
    const setDownloadButtons = document.querySelectorAll('.set-download-btn');
    if (setDownloadButtons.length > 0) {
        setDownloadButtons.forEach(button => {
            button.addEventListener('click', async function(e) {
                e.preventDefault(); // Prevent default link behavior

                const setId = this.dataset.setId;
                const qrCodeUrl = this.href; // Get the QR code URL from the href
                 const filenameElement = this.closest('.list-group-item').querySelector('div h6'); // Assuming set name is in h6
                 let setFilename = 'set'; // Default filename
                 if (filenameElement) {
                     setFilename = filenameElement.textContent.trim().replace(/\s+/g, '_').toLowerCase(); // Get set name and format for filename
                 }
                 const filename = `${setFilename}_qr.png`; // Set desired filename


                if (setId) {
                    // Increment the download count
                    try {
                        fetch(`/increment-set-download/${setId}`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            }
                        });
                    } catch (error) {
                        console.error('Error incrementing set download count:', error);
                        // Continue with download even if tracking fails
                    }
                }

                // Use the generic download function
                if (qrCodeUrl && qrCodeUrl !== '#') {
                    await downloadQrCode(button, qrCodeUrl, filename);
                } else {
                    alert('QR code URL not available.');
                }
            });
        });
    }
});
