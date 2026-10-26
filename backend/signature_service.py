import os
import base64

LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "assets", "ensaan_logo.png")

def get_logo_base64() -> str:
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

def get_active_signature_html(use_base64_img: bool = True) -> str:
    """
    Returns the exact active HTML email signature with clickable links,
    proper font styling, and logo.
    """
    if use_base64_img:
        b64 = get_logo_base64()
        img_src = f"data:image/png;base64,{b64}" if b64 else "/static/assets/ensaan_logo.png"
    else:
        img_src = "/static/assets/ensaan_logo.png"

    html = f"""
<div class="active-email-signature" style="font-family: Arial, Helvetica, sans-serif; font-size: 10pt; line-height: 1.4; color: #000000; margin-top: 20px; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 15px;">
  <p style="margin: 0 0 14px 0; color: #000000;">Best Regards,</p>

  <p style="margin: 0; font-weight: bold; font-size: 10.5pt; color: #000000;">Muhammad Irfan</p>
  <p style="margin: 0; color: #000000;">Regional Sales Manager &ndash; KSA &amp; Bahrain</p>
  <p style="margin: 0; color: #000000;">AlEqtesad Building, Olaya Street</p>
  <p style="margin: 0 0 12px 0; color: #000000;">Riyadh, Kingdom of Saudi Arabia</p>

  <p style="margin: 0; color: #000000;">
    <a href="tel:+966542828945" style="color: #000000; text-decoration: none;">+966 54 2828945</a>
  </p>
  <p style="margin: 0;">
    <a href="mailto:mirfan@ensaantech.com" style="color: #0563C1; text-decoration: underline;">mirfan@ensaantech.com</a>
  </p>
  <p style="margin: 0 0 14px 0;">
    <a href="https://www.linkedin.com/in/irfeepk/" target="_blank" rel="noopener noreferrer" style="color: #0563C1; text-decoration: underline;">linkedin.com/in/irfeepk/</a>
  </p>

  <p style="margin: 0 0 4px 0;">
    <a href="https://www.ensaantech.com" target="_blank" rel="noopener noreferrer" style="text-decoration: none; display: inline-block;">
      <img src="{img_src}" alt="ENSAAN HR TECHNOLOGIES" width="118" height="27" style="border: 0; display: block; max-width: 118px; height: auto;" />
    </a>
  </p>
  <p style="margin: 0 0 14px 0;">
    <a href="https://www.ensaantech.com" target="_blank" rel="noopener noreferrer" style="color: #0563C1; text-decoration: underline; font-size: 10pt;">www.ensaantech.com</a>
  </p>

  <p style="margin: 0 0 10px 0; font-weight: bold; font-size: 9pt; color: #0F243E; letter-spacing: 0.5px;">
    RIYADH &nbsp;|&nbsp; JEDDAH &nbsp;|&nbsp; MANAMA &nbsp;|&nbsp; DUBAI &nbsp;|&nbsp; ABU DHABI &nbsp;|&nbsp; DOHA
  </p>

  <p style="margin: 0 0 4px 0; font-size: 9pt; color: #948A54;">
    Strategic Workforce Planning &nbsp;|&nbsp; Learning Management and Experience Platform &nbsp;|&nbsp; Learning Content
  </p>
  <p style="margin: 0; font-size: 9pt; color: #948A54;">
    Performance &nbsp;|&nbsp; Recruitment &nbsp;|&nbsp; Employee Engagement, Rewards &amp; Recognition &nbsp;|&nbsp; People Analytics
  </p>
</div>
"""
    return html.strip()
