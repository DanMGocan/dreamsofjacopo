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

    // Smooth scroll to features section when clicking on any anchor with href="#features"
    const featureLinks = document.querySelectorAll('a[href="#features"]');
    featureLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            document.getElementById('features').scrollIntoView({ behavior: 'smooth' });
        });
    });
});
