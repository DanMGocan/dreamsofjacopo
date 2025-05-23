# low priority 
## medium priority
### high priority


################## TODO ######################
# ------------------------------------------ #
## Fix registration emails not sent 
# Do not forget to replace admin@slidepull.net with admin@slidepull.com
# Cron jobs to clear the blob and DB of data no longer in use 
# Invalid password error 
# Implement Apple Login
# Implement LinkedIn Login
# Mention SAS Token 
# Member since needs to be properly culled 
## Try and add Bootstrap and other dependencies locally, rather than CDN serving (Bootstrap, fonts)
## Disable developer mode in cloudflare before going live 
# On presentation delete, do not hold the user on same page 


################ DONE ######################
# Add CAPTCHA to the registration page to prevent spam registrations
# Impose password verifications when registering 
### The SAS tokens for the QR codes are not automatically refreshed and they expire after a week
### SAS tokens are exposed in the URL - must have a slidepull URL that points to the Azure Blob links
# We need to remove the email address from the Dashboard and instead, cut the email address just before the @ so it still displays the name of the user.
## Fixed issue with set sizes being much larger than original presentations by implementing image resizing and PDF compression
