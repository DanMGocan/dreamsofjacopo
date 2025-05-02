document.addEventListener('DOMContentLoaded', function() {
    // Get all social login buttons (except Google) and other not implemented features
    const socialLoginButtons = document.querySelectorAll('.social-login');
    const notImplementedButtons = document.querySelectorAll('.not-implemented');

    // Function to show the modal
    function showNotImplementedModal(e) {
        e.preventDefault();
        const modal = new bootstrap.Modal(document.getElementById('notImplementedModal'));
        modal.show();
    }

    // Add click event listener to social login buttons (except Google)
    socialLoginButtons.forEach(button => {
        button.addEventListener('click', showNotImplementedModal);
    });

    // Add click event listener to other not implemented buttons
    notImplementedButtons.forEach(button => {
        button.addEventListener('click', showNotImplementedModal);
    });

    // Add password confirmation validation
    const registrationForm = document.getElementById('registrationForm');
    const passwordInput = document.getElementById('reg-password');
    const confirmPasswordInput = document.getElementById('confirm-password');
    const passwordMismatchError = document.getElementById('password-mismatch-error');

    if (registrationForm && passwordInput && confirmPasswordInput && passwordMismatchError) {
        registrationForm.addEventListener('submit', function(event) {
            if (passwordInput.value !== confirmPasswordInput.value) {
                event.preventDefault(); // Prevent form submission
                passwordMismatchError.style.display = 'block'; // Show error message
                confirmPasswordInput.classList.add('is-invalid'); // Add red border
            } else {
                passwordMismatchError.style.display = 'none'; // Hide error message
                confirmPasswordInput.classList.remove('is-invalid'); // Remove red border
            }
        });

        // Optional: Hide error message when user starts typing again
        confirmPasswordInput.addEventListener('input', function() {
            if (passwordMismatchError.style.display === 'block') {
                passwordMismatchError.style.display = 'none';
                confirmPasswordInput.classList.remove('is-invalid');
            }
        });
         passwordInput.addEventListener('input', function() {
            if (passwordMismatchError.style.display === 'block') {
                passwordMismatchError.style.display = 'none';
                confirmPasswordInput.classList.remove('is-invalid');
            }
        });
    }

    // Special handling for the "Get Started" button to scroll to login section after showing modal
    const getStartedButton = document.querySelector('[data-feature="get-started"]');
    if (getStartedButton) {
        getStartedButton.addEventListener('click', function(e) {
            e.preventDefault();

            // Show the modal
            const modal = new bootstrap.Modal(document.getElementById('notImplementedModal'));
            modal.show();

            // After modal is hidden, scroll to login section
            document.getElementById('notImplementedModal').addEventListener('hidden.bs.modal', function () {
                document.getElementById('login').scrollIntoView({ behavior: 'smooth' });
            }, { once: true });
        });
    }

    // Special handling for the "Learn More" button to scroll to features section after showing modal
    const learnMoreButton = document.querySelector('[data-feature="learn-more"]');
    if (learnMoreButton) {
        learnMoreButton.addEventListener('click', function(e) {
            e.preventDefault();

            // Show the modal
            const modal = new bootstrap.Modal(document.getElementById('notImplementedModal'));
            modal.show();

            // After modal is hidden, scroll to features section
            document.getElementById('notImplementedModal').addEventListener('hidden.bs.modal', function () {
                document.getElementById('features').scrollIntoView({ behavior: 'smooth' });
            }, { once: true });
        });
    }
});
