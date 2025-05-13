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
    
    // Add hover effect to social login buttons
    const socialButtons = document.querySelectorAll('.btn-google, .btn-linkedin, .btn-apple');
    socialButtons.forEach(button => {
        button.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px)';
        });
        
        button.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });

    // Add password confirmation validation
    const registrationForm = document.getElementById('registrationForm');
    const passwordInput = document.getElementById('reg-password');
    const confirmPasswordInput = document.getElementById('confirm-password');
    const passwordMismatchError = document.getElementById('password-mismatch-error');

    if (registrationForm && passwordInput && confirmPasswordInput && passwordMismatchError) {
        registrationForm.addEventListener('submit', function(event) {
            // Only check password match here, reCAPTCHA v3 is handled by the button's data-callback
            if (passwordInput.value !== confirmPasswordInput.value) {
                event.preventDefault(); // Prevent form submission
                passwordMismatchError.style.display = 'block'; // Show error message
                confirmPasswordInput.classList.add('is-invalid'); // Add red border
            } else {
                passwordMismatchError.style.display = 'none'; // Hide error message
                confirmPasswordInput.classList.remove('is-invalid'); // Remove red border
                // Form will be submitted by reCAPTCHA callback
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

    // Smooth scroll for all anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            if (this.getAttribute('href').length > 1) { // Ignore links that are just "#"
                e.preventDefault();
                const targetId = this.getAttribute('href');
                const targetElement = document.querySelector(targetId);
                
                if (targetElement) {
                    targetElement.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });

    // Add interactive floating slides
    const floatingSlides = document.querySelectorAll('.floating-slide');
    
    // Make slides slightly interactive on mousemove
    document.addEventListener('mousemove', function(e) {
        const mouseX = e.clientX / window.innerWidth;
        const mouseY = e.clientY / window.innerHeight;
        
        floatingSlides.forEach(slide => {
            const offsetX = (mouseX - 0.5) * 20;
            const offsetY = (mouseY - 0.5) * 20;
            
            // Apply a subtle transform based on mouse position
            slide.style.transform = `translateX(${offsetX}px) translateY(${offsetY}px) rotate(var(--rotation))`;
        });
    });

    // Reset transforms when mouse leaves the container
    document.querySelector('.hero-container').addEventListener('mouseleave', function() {
        floatingSlides.forEach(slide => {
            slide.style.transform = 'rotate(var(--rotation))';
        });
    });

    // Add intersection observer for animation triggers
    const animatedElements = document.querySelectorAll('.process-step, .feature-card');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate__animated', 'animate__fadeInUp');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.2
    });
    
    animatedElements.forEach(element => {
        observer.observe(element);
    });
});
