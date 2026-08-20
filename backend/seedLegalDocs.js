// seedLegalDocs.js

import mongoose from "mongoose";
import dotenv from "dotenv";
import LegalDoc from "./models/LegalDoc.js";

dotenv.config();


// =========================================================
// DATABASE
// =========================================================

const seedLegalDocs = async () => {
  try {
    if (!process.env.MONGO_URI) {
      throw new Error("MONGO_URI is not configured.");
    }

    await mongoose.connect(process.env.MONGO_URI);

    console.log("✅ MongoDB connected");


    // =====================================================
    // RESET CURRENT LEGAL DOCUMENTS
    // =====================================================

    await LegalDoc.deleteMany({});


    // =====================================================
    // PRIVACY POLICY
    // =====================================================

    await LegalDoc.create({
      type: "privacy",

      version: "2.0",

      content: `
## RevelaCode & Jumuiya Privacy Policy

**Effective Date: August 20, 2026**

At **RevelaCode**, we respect your privacy and are committed to protecting your personal information.

RevelaCode is a technology platform providing faith, Bible, learning and related digital services. **Jumuiya** is an ecosystem within the RevelaCode platform that provides business, agriculture, education, marketplace, community and related services.

This Privacy Policy explains how we collect, use, store, protect and otherwise process personal information when you access or use RevelaCode, Jumuiya, our websites, applications, APIs and related services.

This policy should be read together with our Terms of Service.

---

### 1. Who We Are

The platform is operated under:

**RevelaCode Software Studio**

RevelaCode includes the broader Jumuiya ecosystem and its associated services.

Where applicable, references to "RevelaCode", "we", "us" or "our" include the RevelaCode platform and Jumuiya services.

---

### 2. Information We Collect

We may collect information necessary to provide and secure our services.

#### A. Information You Provide

This may include:

- Full name
- Phone number or other contact information
- Email address
- Account credentials
- Profile information
- County, town or location information
- Business information
- Farm and agricultural information
- Education-related information
- Marketplace listings
- Community posts and comments
- Saved content and preferences
- Transaction and payment-related information
- Support requests
- Information you voluntarily submit through forms or other platform features

#### B. Information Generated Through Use

We may collect:

- Login and authentication events
- Feature usage
- Account activity
- Transaction records
- Marketplace activity
- Community activity
- Application diagnostics
- Error logs
- Timestamps
- Device and browser information
- IP address and security information where technically necessary

#### C. Information From Connected Services

Where you choose to connect another service or account, we may receive information from that service in accordance with your authorization and the applicable provider's policies.

---

### 3. Information Used by Jumuiya

Jumuiya is integrated into RevelaCode and uses the existing RevelaCode account identity.

A single RevelaCode account may participate in different Jumuiya services, including:

- Biashara
- Shamba
- Elimu
- Marketplace
- Community
- Wallet and transaction records

Jumuiya may process information necessary for the particular service you choose to use.

For example:

**Biashara**
- Business profile
- Products
- Customers
- Orders
- Inventory
- Sales
- Expenses

**Shamba**
- Farmer profile
- Farm information
- Crops
- Farm activities
- Harvest records
- Agricultural listings

**Elimu**
- Education profile
- School information
- Classes
- Lessons
- Assignments
- Educational projects
- Fee records where applicable

**Marketplace**
- Listings
- Seller information
- Product or service information
- Orders
- Transaction references

**Community**
- Posts
- Comments
- Reactions
- Reports and moderation records

We only seek to collect information that is relevant and reasonably necessary for the service being provided.

---

### 4. How We Use Personal Information

We may use personal information to:

- Create and manage accounts
- Authenticate users
- Provide RevelaCode services
- Provide Jumuiya services
- Maintain business, farm and education functionality
- Facilitate marketplace interactions
- Maintain transaction and payment records
- Provide notifications
- Personalize platform settings
- Maintain user history
- Improve platform functionality
- Protect accounts and systems
- Detect fraud, abuse and unauthorized activity
- Investigate security incidents
- Provide customer support
- Maintain audit records
- Comply with applicable legal obligations

We do not use personal information for purposes incompatible with the purposes for which it was collected unless permitted or required by applicable law.

---

### 5. Legal Basis and Fair Processing

We aim to process personal information lawfully, fairly and transparently.

Depending on the circumstances, processing may be necessary for:

- Providing a service requested by you
- Fulfilling contractual obligations
- Compliance with legal obligations
- Protecting legitimate interests
- Preventing fraud and security abuse
- Other lawful grounds permitted under applicable law

Under Kenyan data protection law, personal data should be processed lawfully, fairly and transparently, collected for specified purposes, limited to what is necessary, kept accurate and retained only as long as necessary. 

---

### 6. Sharing of Information

We do **not sell your personal data**.

We may share limited information with:

- Hosting and infrastructure providers
- Database and storage providers
- Authentication and security providers
- Payment providers
- Communication providers
- Analytics or diagnostic providers where applicable
- Professional advisers
- Law enforcement or regulatory authorities where legally required
- Other parties where disclosure is necessary to protect our rights, users or systems

Service providers processing information on our behalf are expected to handle information under appropriate confidentiality and data protection arrangements.

---

### 7. Marketplace and Community Information

Some Jumuiya information is intentionally designed to be visible to other users.

For example, when you publish a marketplace listing, other users may see information associated with that listing.

When you publish a Community post, other users may see:

- Your public profile information
- Post content
- Location information you chose to provide
- Comments or reactions associated with the post

You should not publish sensitive personal information, passwords, financial credentials or another person's private information in public areas of the platform.

---

### 8. Payments and Financial Information

Jumuiya may maintain transaction records associated with payments, purchases, school fees, farm inputs, marketplace activity or business operations.

Where third-party payment providers are used, payment processing may be performed by those providers under their own terms and privacy policies.

RevelaCode does not intentionally store payment-card credentials unless specifically required and lawfully configured for the applicable service.

Transaction records may include:

- Amount
- Currency
- Transaction type
- Reference
- Date and time
- Related service or transaction status

---

### 9. Children's and Minors' Information

Some Jumuiya services, particularly **Elimu**, may involve children or students.

Where information relates to a child, we apply additional safeguards required by applicable law.

Under Kenya's Data Protection Act, rights concerning a minor may be exercised by a person with parental authority or a guardian in the circumstances specified by law. Kenyan law also provides additional safeguards concerning children's personal information. 

We do not knowingly use children's personal data for unrelated purposes.

Parents, guardians, schools and other authorized persons should ensure that information submitted about children is accurate and that they have the necessary authority to provide it.

Certain features or transactions may have additional age, parental authorization or eligibility requirements.

---

### 10. Data Security

We implement reasonable technical and organizational safeguards designed to protect personal information against:

- Unauthorized access
- Unauthorized disclosure
- Loss
- Destruction
- Alteration
- Misuse

Security measures may include:

- Authentication controls
- Access controls
- Encrypted communications
- Logging and monitoring
- Database security
- Backups
- Audit records
- Security reviews

No internet-connected system can be guaranteed to be completely secure.

---

### 11. Data Retention

We retain personal information only for as long as reasonably necessary for:

- Providing our services
- Maintaining account records
- Security and fraud prevention
- Resolving disputes
- Maintaining financial or transaction records
- Complying with legal obligations
- Establishing, exercising or defending legal claims

When information is no longer reasonably required, we may delete, anonymize or otherwise securely dispose of it, subject to applicable legal requirements.

---

### 12. Your Data Protection Rights

Subject to applicable law, you may have rights to:

- Be informed about processing of your personal information
- Access personal information held about you
- Request correction of inaccurate or misleading information
- Object to certain processing
- Request deletion or erasure in applicable circumstances
- Request restriction of processing where applicable
- Exercise applicable rights through an authorized representative

Kenya's Data Protection Act expressly provides several of these rights, including information, access, objection, correction and deletion rights. :contentReference[oaicite:1]{index=1}

Requests involving children's data may be subject to additional requirements regarding parental or guardian authority.

---

### 13. Account Deletion

You may request deletion of your account or applicable personal information.

Some information may need to be retained where required by law or where retention is necessary for legitimate purposes such as fraud prevention, dispute resolution, accounting or legal claims.

---

### 14. International Data Transfers

Some infrastructure or service providers may process information outside Kenya.

Where personal information is transferred outside Kenya, we seek to apply appropriate safeguards and comply with applicable data protection requirements.

Kenya's Data Protection Act includes requirements concerning transfers of personal data outside Kenya and appropriate safeguards. :contentReference[oaicite:2]{index=2}

---

### 15. Cookies and Similar Technologies

RevelaCode may use cookies, local storage or similar technologies to:

- Maintain sessions
- Remember preferences
- Improve user experience
- Maintain security
- Understand service usage

Users may be able to manage certain browser or device settings affecting these technologies.

---

### 16. Changes to This Privacy Policy

We may update this Privacy Policy when our services, technology or legal obligations change.

When material changes occur, we may provide appropriate notice through the platform or other reasonable communication channels.

The effective date shown at the beginning of this policy indicates the current version.

---

### 17. Contact

For privacy questions, requests or concerns, contact:

**RevelaCode Software Studio**

**Email:** support@revelacode.com

We will handle privacy requests in accordance with applicable data protection requirements.

---

### 18. Important Notice

This Privacy Policy describes our intended privacy practices and does not replace applicable law.

Where applicable law provides stronger rights or protections than this policy, the applicable law will prevail.
`.trim(),
    });


    // =====================================================
    // TERMS OF SERVICE
    // =====================================================

    await LegalDoc.create({
      type: "terms",

      version: "2.0",

      content: `
## RevelaCode & Jumuiya Terms of Service

**Effective Date: August 20, 2026**

Welcome to **RevelaCode**.

RevelaCode provides digital services relating to Bible study, theology, learning and related technology.

**Jumuiya** is an ecosystem within RevelaCode that provides business, farming, education, marketplace, community and related services.

By accessing or using RevelaCode or Jumuiya, you agree to these Terms of Service.

If you do not agree with these Terms, do not use the applicable service.

---

### 1. About the Platform

RevelaCode may provide:

- Bible and scripture resources
- Theology and faith-related tools
- Study resources
- Educational features
- Digital research and reference tools
- AI-assisted features where available

Jumuiya may provide:

- Biashara business services
- Shamba agricultural services
- Elimu education services
- Marketplace services
- Community services
- Transaction and payment-related services
- Notifications and communication features

Individual features may have additional terms.

---

### 2. Eligibility

You must meet the minimum eligibility requirements applicable to the service you are using.

Some services may impose additional age or authorization requirements.

Certain education, marketplace, payment or financial-related features may require parental, guardian, institutional or other authorization where required by law.

We may restrict access to particular features where required by applicable law or for safety and security reasons.

---

### 3. Your Account

You are responsible for:

- Providing accurate information
- Protecting your login credentials
- Keeping your account information reasonably current
- Not sharing authentication credentials
- Reporting suspected unauthorized access

You are responsible for activities performed through your account except where unauthorized activity resulted from circumstances beyond your reasonable control and was reported appropriately.

---

### 4. Acceptable Use

You agree to use RevelaCode and Jumuiya only for lawful purposes.

You must not:

- Hack, attack or attempt to disrupt the platform
- Circumvent authentication or security controls
- Access another user's account without authorization
- Upload malware
- Scrape or extract platform data without permission
- Abuse APIs or automated services
- Manipulate transactions
- Attempt to create fraudulent balances
- Impersonate another person
- Harass or threaten other users
- Publish unlawful or harmful content
- Use marketplace services for prohibited transactions
- Violate applicable laws or regulations
- Attempt to reverse engineer restricted systems
- Interfere with normal platform operations

---

### 5. RevelaCode Content

RevelaCode may provide:

- Bible text
- Commentary
- Study resources
- Educational material
- Prophecy tools
- Reference information

Unless otherwise stated, platform-owned software, design, branding and proprietary content remain the property of RevelaCode or the applicable rights holder.

Third-party materials remain subject to their respective rights and licenses.

---

### 6. User-Generated Content

You may submit:

- Notes
- Posts
- Comments
- Marketplace listings
- Business information
- Farm information
- Educational information
- Other permitted content

You retain rights you have in content you submit, subject to applicable third-party rights.

By submitting content, you grant RevelaCode the limited rights reasonably necessary to:

- Host it
- Store it
- Process it
- Display it as intended by the relevant service
- Provide the associated feature
- Maintain security
- Perform necessary technical operations

You must have the necessary rights and authority to submit the content.

---

### 7. Community Rules

Community features are intended to support constructive communication.

You must not use Community features to:

- Harass users
- Threaten people
- Spread malicious content
- Publish private information without authorization
- Engage in fraud
- Spam
- Impersonate others
- Promote unlawful activities

We may remove or restrict content that violates these Terms or applicable law.

---

### 8. Marketplace

Jumuiya Marketplace may allow users to publish listings for goods or services.

Sellers are responsible for:

- Accurate descriptions
- Accurate pricing
- Availability information
- Legal compliance
- Fulfillment of accepted transactions
- Their relationship with buyers

RevelaCode is a technology platform and may not be the seller, buyer, owner or provider of every item or service listed.

Certain goods and services may be prohibited or restricted.

We may suspend or remove listings that violate our rules or applicable law.

---

### 9. Business and Agricultural Services

Biashara and Shamba may allow users to maintain:

- Business records
- Inventory
- Sales
- Expenses
- Farm records
- Crops
- Harvest information
- Marketplace listings

Users are responsible for the accuracy of information they enter.

RevelaCode does not guarantee commercial results, agricultural yields, profitability, market prices or availability.

---

### 10. Education Services

Elimu may provide services for:

- Students
- Parents
- Teachers
- Schools
- Learning activities
- Assessments
- Projects
- Educational materials

Schools, teachers, parents and other authorized users are responsible for ensuring that information submitted about students is accurate and appropriately authorized.

Certain education services may require additional institutional or parental controls.

---

### 11. Payments and Transactions

Where payment services are available, payments may be processed through third-party providers.

A transaction may have statuses such as:

- Pending
- Processing
- Completed
- Failed
- Cancelled
- Reversed

A platform transaction record does not necessarily mean that a payment provider has successfully transferred funds until the applicable payment confirmation has been verified.

Users must not attempt to manipulate transaction records or payment statuses.

---

### 12. Fees and Charges

Certain services may be free while others may involve:

- Subscription charges
- Listing fees
- Transaction fees
- Advertising charges
- Service charges

Any applicable charges should be communicated before the relevant transaction is completed.

---

### 13. Third-Party Services

RevelaCode may integrate with third-party services such as:

- Payment providers
- Hosting providers
- Authentication providers
- Maps
- Communication providers
- Storage providers
- Analytics services

Third-party services may operate under their own terms and privacy policies.

---

### 14. Availability

We aim to provide reliable services but do not guarantee uninterrupted availability.

Services may occasionally be unavailable because of:

- Maintenance
- Network failures
- Infrastructure failures
- Security incidents
- Third-party provider failures
- Events beyond our reasonable control

---

### 15. Security

You must not attempt to bypass security controls or obtain unauthorized access.

We may suspend access when reasonably necessary to protect users, data, systems or the integrity of the platform.

---

### 16. Suspension and Termination

We may suspend, restrict or terminate access where:

- These Terms are violated
- Fraud is suspected
- Security is threatened
- A user abuses the platform
- Required by law
- Necessary to protect users or the platform

Where appropriate, we may provide notice or an opportunity to resolve the issue.

---

### 17. Disclaimers

RevelaCode and Jumuiya are provided on an **"as available"** and, where permitted by law, **"as is"** basis.

We do not guarantee:

- That every service will always be available
- That information will always be error-free
- That marketplace listings are accurate
- That business activities will be profitable
- That agricultural activities will achieve a particular yield
- That educational outcomes will meet a particular result
- That third-party services will always operate

Faith, educational, agricultural, business or other informational content should not be treated as a substitute for professional advice where professional advice is required.

---

### 18. Limitation of Liability

To the maximum extent permitted by applicable law, RevelaCode will not be responsible for indirect, incidental, special or consequential losses arising from use of the platform.

Nothing in these Terms excludes liability that cannot lawfully be excluded or limited.

---

### 19. Changes to the Terms

We may update these Terms as our services, technology or legal obligations change.

Material updates may be communicated through the platform or other appropriate channels.

Continued use of the relevant services after an effective update may constitute acceptance of the updated Terms to the extent permitted by law.

---

### 20. Governing Law

These Terms are intended to operate subject to the applicable laws of the Republic of Kenya and any other mandatory laws applicable to a particular user or transaction.

---

### 21. Contact

For questions regarding these Terms:

**RevelaCode Software Studio**

**Email:** support@revelacode.com

---

### 22. Final Notice

These Terms describe the general rules governing use of RevelaCode and Jumuiya.

Certain features may have additional rules, notices, agreements or policies that apply specifically to those services.
`.trim(),
    });


    // =====================================================
    // SUCCESS
    // =====================================================

    console.log(
      "✅ RevelaCode & Jumuiya legal documents seeded successfully!"
    );

    console.log(
      "✅ Privacy Policy v2.0"
    );

    console.log(
      "✅ Terms of Service v2.0"
    );

    await mongoose.disconnect();

    process.exit(0);

  } catch (err) {

    console.error(
      "❌ Failed to seed legal docs:",
      err
    );

    try {
      await mongoose.disconnect();
    } catch (_) {
      // Ignore disconnect errors during failure handling.
    }

    process.exit(1);
  }
};


seedLegalDocs();