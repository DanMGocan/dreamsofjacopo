document.addEventListener('DOMContentLoaded', function() {
    // Initialize any tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

/**
 * Check if the user is eligible to downgrade to a lower tier
 * @param {number} targetTier - The tier to downgrade to (0 for Free, 1 for Premium)
 * @param {string} tierName - The name of the tier for display purposes
 */
function checkDowngradeEligibility(targetTier, tierName) {
    // First confirm the user wants to downgrade
    if (confirm(`Are you sure you want to downgrade to ${tierName} tier? This will take effect immediately.`)) {
        // Make an AJAX request to check eligibility
        fetch(`/check-downgrade-eligibility/${targetTier}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.eligible) {
                // If eligible, redirect to the upgrade page with downgrade parameter
                window.location.href = `/upgrade?downgrade=${targetTier}`;
            } else {
                // If not eligible, show the error message
                alert(data.message);
            }
        })
        .catch(error => {
            console.error('Error checking downgrade eligibility:', error);
            alert('An error occurred while checking downgrade eligibility. Please try again later.');
        });
    }
}
