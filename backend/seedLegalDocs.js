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

**Effective Date: July 25, 2025**

At **RevelaCode**, we take your privacy seriously. This Privacy Policy describes how we collect, process, store, and protect your personal information when you access or use our platform, services, and features.

### **1. Information We Collect**
We may collect the following categories of information:

**A. Information You Provide**
- Account details (e.g., name, email, authentication credentials)
- Linked third-party accounts (e.g., Google, TikTok, Facebook, Instagram, WhatsApp)
- Content you generate within RevelaCode (e.g., saved decodes, annotations, preferences)

**B. Automatically Collected Information**
- Usage data (e.g., interactions, feature engagement, timestamps)
- Device information (e.g., browser type, IP address, operating system)
- Diagnostic and performance data

### **2. How We Use Your Information**
We use your data to:
- Deliver, maintain, and improve RevelaCode’s services  
- Personalize your experience and recommendations  
- Enhance security, prevent fraud, and detect misuse  
- Conduct analytics to optimize platform performance  
- Provide customer support and resolve issues  

### **3. Data Sharing and Disclosure**
We **do not sell your personal data.** We may share information only with:
- Trusted service providers that support platform operations (hosting, analytics, security)
- Legal authorities when required by law or to protect our rights
- Partners strictly under confidentiality and data protection agreements

### **4. Data Security**
We implement industry-standard security measures to protect your data, including encryption, access controls, and regular system monitoring. However, no system is 100% secure.

### **5. Your Rights**
You have the right to:
- Access, update, or delete your personal data  
- Export your data in a readable format  
- Withdraw consent for certain types of processing  
- Request restriction of data processing where applicable  

### **6. Data Retention**
We retain your data only as long as necessary to provide our services or comply with legal obligations.

### **7. Contact Us**
For questions or concerns regarding this Privacy Policy, contact us at:  
**support@revelacode.com**
  `.trim(),
      version: '1.0'
      },
      {
  type: 'terms',
  content: `
## Terms of Service

**Effective Date: July 25, 2025**

Welcome to **RevelaCode.** By accessing or using our platform, you agree to comply with and be bound by these Terms of Service.

### **1. Eligibility**
You must be at least **13 years old** to use RevelaCode. By using the platform, you confirm that you meet this requirement.

### **2. Permitted Use**
You agree to use RevelaCode for lawful and intended purposes only. You must **not**:
- Attempt to hack, disrupt, or reverse engineer our systems  
- Scrape, automate, or extract data without authorization  
- Spam, harass, or exploit other users  
- Use RevelaCode for illegal activities  

### **3. User Content**
- You retain ownership of your decodes, notes, and contributions  
- By using RevelaCode, you grant us a limited, non-exclusive license to process your content for service improvement  
- We may use **anonymized** data for analytics and research  

### **4. Account Responsibility**
- You are responsible for maintaining the confidentiality of your login credentials  
- Any activity under your account is your responsibility  
- Notify us immediately if you suspect unauthorized access  

### **5. Service Availability**
We strive to provide uninterrupted service but do not guarantee that RevelaCode will always be error-free or available.

### **6. Termination**
We reserve the right to suspend or terminate your access if you violate these Terms or engage in harmful behavior.

### **7. Disclaimer of Warranties**
RevelaCode is provided **“as is.”** We disclaim all warranties, express or implied, including fitness for a particular purpose.

### **8. Limitation of Liability**
To the maximum extent permitted by law, RevelaCode shall not be liable for any indirect, incidental, or consequential damages arising from your use of the platform.

### **9. Contact**
For inquiries, contact: **support@revelacode.com**
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
