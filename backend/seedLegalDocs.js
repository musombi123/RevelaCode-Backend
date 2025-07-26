// seedLegalDocs.js
import mongoose from 'mongoose';
import dotenv from 'dotenv';
import LegalDoc from './models/LegalDoc.js';

dotenv.config();

const seedLegalDocs = async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);

    await LegalDoc.deleteMany(); // optional: clear old docs for fresh seed

    await LegalDoc.create([
      {
        type: 'privacy',
        content: `
## Privacy Policy

Effective Date: July 25, 2025

At RevelaCode, your privacy is important to us. This Privacy Policy explains how we collect, use, and protect your personal data when you use our platform.

**Information We Collect**
- Account details (e.g., email, linked social media)
- Usage data (e.g., logs, device info)
- Any data you choose to share (e.g., saved decodes)

**How We Use Your Data**
- To provide and improve the RevelaCode experience
- To personalize content based on your preferences
- For security, support, and analytics

**Data Sharing**
We do **not** sell your data. We may share data only with trusted partners who help us operate RevelaCode, subject to strict confidentiality.

**Your Rights**
- Access, update, or delete your data at any time
- Withdraw consent for processing

**Contact**
For questions, contact us at: support@revelacode.com
      `.trim(),
        version: '1.0'
      },
      {
        type: 'terms',
        content: `
## Terms of Service

Effective Date: July 25, 2025

Welcome to RevelaCode! By using our platform, you agree to these Terms.

**1. Use of Service**
- You must be at least 13 years old
- Do not misuse RevelaCode (e.g., hacking, spamming, scraping)

**2. Content**
- You retain ownership of your decodes and notes
- RevelaCode may use anonymized data to improve the service

**3. Account**
- Keep your credentials confidential
- You are responsible for activity under your account

**4. Termination**
We may suspend or terminate your access if you violate these Terms.

**5. Disclaimer**
RevelaCode is provided “as is” without warranties. We are not liable for any indirect damages.

**Contact**
Questions? Email support@revelacode.com
      `.trim(),
        version: '1.0'
      }
    ]);

    console.log('✅ Legal docs seeded successfully!');
    process.exit();
  } catch (err) {
    console.error('❌ Failed to seed legal docs:', err);
    process.exit(1);
  }
};

seedLegalDocs();
