Python 3.12.4

Libraries to add:
- error logging
- performance tracking

Apps to install
- LibreOffice
- MySQL

What do with .odt format?

File upload validation (size and #of slides)

Max 40 slides for the free tier, max 150 for paid tier

SQLite to be used at first, might migrate later, dunno

Send a message to the users to close their .pptx if it doesn't work to upload it

Have a separate VM for DB and Webapplication, once latency becomes a problem

Move all the passwords to a .env file once in production
Must make sure unique names are created for the .pptx file
Different formats might require different upload forms
Check for number of slides and size

Add Azure integration

Should we make images available as full .pdfs to downloads?

Should I use a queue system like Celery to queue tasks and send notifications to user when they can download their set? 
Should I use Celety for background conversion 

Database and VM backup 

This is a common problem when:

The application does not verify authorization beyond authentication (i.e., the user is logged in but not restricted to their own data).
The API relies solely on the client to provide resource identifiers, which can be easily manipulated.
Make sure that access to resources is conditioned by the owner_id matching the owner of the resource id. 