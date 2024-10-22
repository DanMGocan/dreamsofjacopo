6. Additional Security Considerations
Input Validation:

Sanitize user inputs to prevent SQL injection.
Using parameterized queries (which we did) helps prevent injection attacks.
HTTPS:

Ensure your website uses HTTPS to encrypt data in transit.
This prevents attackers from intercepting sensitive data like passwords.
Session Management:

Use secure methods to manage user sessions (e.g., JWTs, secure cookies).
Protect against session hijacking and fixation.
Account Verification (Optional):

Implement email verification to confirm user emails.
This helps prevent spam accounts and ensures valid email addresses.
Rate Limiting:

Implement rate limiting on your endpoints to prevent brute-force attacks.
Password Policies:

Enforce strong password requirements (minimum length, complexity).
Educate users on creating secure passwords.

Test the three login methods, to make sure they do not allow cross login. 

Have a mechanism to regenerate SAS Tokens on request