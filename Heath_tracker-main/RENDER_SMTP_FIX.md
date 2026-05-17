# SMTP Configuration Fix for Render Deployment

## Problem
When deploying to Render, the registration endpoint fails with SMTP connection errors:
```
socket.create_connection failed
SystemExit: 1
Worker exiting
```

This happens because:
1. **Missing or incorrect SMTP environment variables** on Render
2. **No timeout on SMTP connection** - connection hangs indefinitely
3. **Gunicorn kills the worker** after timeout

## Solution

### Step 1: Code Fix (Already Applied)
✅ Updated `utils.py` with:
- **10-second timeout** on SMTP connection to prevent hanging
- **Better error handling** for SMTP authentication and connection errors
- **Detailed logging** to identify the exact problem

### Step 2: Configure SMTP on Render

Go to your Render project dashboard and add these **Environment Variables**:

#### Option A: Using Gmail (Recommended for testing)
```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
```

**To get Gmail App Password:**
1. Enable 2-factor authentication on your Google account
2. Visit: https://myaccount.google.com/apppasswords
3. Select "Mail" and "Windows Computer" 
4. Copy the 16-character password
5. Use this as `MAIL_PASSWORD` (remove spaces)

#### Option B: Using SendGrid (Production Recommended)
```
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=apikey
MAIL_PASSWORD=SG.your_sendgrid_api_key_here
```

#### Option C: Using Office 365
```
MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@company.onmicrosoft.com
MAIL_PASSWORD=your_office365_password
```

### Step 3: Verify Configuration on Render

1. **Redeploy** your service on Render (go to Manual Deploy)
2. **Check logs** for these messages:
   - ✅ `OTP email sent successfully to user@example.com` - Success!
   - ❌ `SMTP authentication failed` - Check credentials
   - ❌ `SMTP connection timeout` - Check if port 587 is accessible

3. **Test registration** at `https://your-app.onrender.com/register`

### Step 4: Fallback Behavior

If SMTP fails, the app will:
- Show user: `"SMTP is not configured. Development OTP: 123456"` 
- Allow registration to proceed with development OTP
- This is intentional - users can still test the app

To truly disable email in production, you can modify the registration route, but it's not recommended.

## Troubleshooting

### "SMTP authentication failed"
- Verify `MAIL_USERNAME` and `MAIL_PASSWORD` are correct
- For Gmail: Use app password, not account password
- For Office 365: Enable "Allow less secure apps" (if applicable)

### "SMTP connection timeout"
- Port 587 might be blocked by Render's network
- Try port 25 or 465 (though less common)
- Or switch to SendGrid/Mailgun which work reliably on Render

### "Mail is not configured. Skipping send"
- One or more of MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD are empty
- Check all 3 are set in Render environment variables

### Worker being killed
- Check Render logs for worker errors
- Previous issue was no timeout - now fixed in code
- If still happening, might be memory issue (upgrade Render plan)

## Deployment Steps

1. Push this code to GitHub (includes timeout fix in utils.py)
2. Go to Render > Environment > Add variables (use one of the options above)
3. Manual Deploy or push to trigger auto-deploy
4. Monitor logs while testing registration
5. Verify email is being sent

## Email HTML Template (Optional Future Enhancement)

Currently sending plain text. To send HTML emails:
```python
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

msg = MIMEMultipart('alternative')
msg.attach(MIMEText(body, 'html'))
```

---

**Need help?** Check your Render logs in real-time:
- Render Dashboard → Your Service → Logs
- Look for messages containing "OTP" or "SMTP"
