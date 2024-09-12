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