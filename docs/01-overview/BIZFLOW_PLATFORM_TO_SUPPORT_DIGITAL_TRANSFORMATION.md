**CAPSTONE PROJECT REGISTER**

**1\. Register information for the supervisor**

**2\. Register information for students**

| Full name  | Student code  | Phone  | Email  | Role in  Group |

| :---: | :---: | ----- | :---: | :---: |
| Lê Minh Thiện |  SE183143 | 0363053659 | thienlmse183143@fpt.edu.vn | Leader |
| Trần Văn Duy | SE183134 | 0325502449 | duytvse183134@fpt.edu.vn | Member |
| Vũ Hoàng Hiếu Ngân | SE183096 | 0966288741 | nganvhhse183096@fpt.edu.vn | Member |
| Lê Minh Khoa | SE180049 | 0868227630 | khoalmse180049@fpt.edu.vn | Member |

**3\. Register the content of the Capstone Project**

**(\*) 3.1. Capstone Project Name:**  
● **English**: Platform to support digital transformation for household businesses.

● **Vietnamese**: Nền tảng hỗ trợ chuyển đổi số cho hộ kinh doanh.

● **Abbreviation**: BizFlow

**a. Context:**

* In Vietnam, household businesses play a critical role in the local economy, especially in traditional sectors such as retail and service stores. The majority of these fall under 1 billion VND per year.  
* Household businesses in Vietnam currently operate using archaic, manual workflows. Daily operations such as recording sales, tracking inventory, and managing complex customer debts are typically documented in handwritten notebooks or disjointed Excel files. A significant volume of their transactions occurs through unstructured channels, including phone calls and Zalo messages, requiring owners to mentally process orders and manually transcribe them.
* The lack of suitable technological alternatives drives this reliance on manual processes. Existing commercial POS solutions are predominantly designed for modern retail chains or the F\&B industry, necessitating a complex hardware ecosystem (computers, barcode scanners, receipt printers) that household businesses neither possess nor can afford. Most owners operate with only a single smartphone and lack the digital literacy required to navigate complex software interfaces.
* What's more, according to Circular 152/2025/TT-BTC, the Ministry of Finance has decided to abolish the presumptive tax method for business households. They are now required to switch to the self-declaration method based on specific accounting book templates. In this context, business households with annual revenue under 1 billion VND shall implement a simplified accounting method, using manual record-keeping (according to Circular 152/2025/TT-BTC, Article 2\. Organization of accounting work). This transition is quite a foreign concept to most household businesses, making it a significant challenge for them to adapt.
* To address this gap, we propose developing **a platform to support digital transformation for household businesses**. The system is specifically designed for traditional retail and service stores, offering an integrated solution that combines order management, inventory tracking, and financial reports. An AI feature (speech to text) supports users by creating draft orders, helping reduce manual work, minimizing mistake and tracking business revenue.

  b. **Proposed Solutions**:

  Build an application (mobile and/or web) that supports the following core functionalities:

* User:
  * Create orders (search products, add quantity, add customer details).  
  * View and confirm "Draft Orders" created by the AI.  
  * Manage product catalog (name, price, multiple units of measure).  
  * Manage business location.  
  * Manage debt (info, purchase history).  
  * View reports and analytics (daily/monthly revenue, best-sellers).  
  * Manage employees.  
* Administrator:  
  * Manage accounts.  
  * View reports and analytics.  
  * Manage Subscription Pricing.  
  * Update system config and templates for financial reports.  
  * Manage notifications.  
* Consultant:  
  * Update templates for financial reports.  
  * Manage notifications.  
* System:  
  * Convert natural language into a draft order.  
  * It automatically does the bookkeeping.  
  * Revenue forecast.  
  * Warning of unusual data.

  ● **Functional requirements**:  

  **User:**

  **● Create Orders:** Users can create orders for customers. They can search for products, select quantity and add items to the order.

  **● View and confirm "Draft Orders" created by the AI:** Users can review the order created by AI and edit if there are defects, then confirm to create the order.

  **● Manage Product Catalog:** The user can create, update, or disable products. They can define product attributes such as name, images, price, category, and multiple units of measure. Pricing rules can also be configured.

  **● Manage Business Location:** The user can record stock imports, track stock levels, and view inventory history. The system automatically deducts stock upon order confirmation.

  **● Manage Debt:** The user can add and update the customer debt profile, view their purchase history, track outstanding debts, and review payment history.

  **● View Reports and Analytics:** Provides interactive dashboards that show daily/weekly/monthly revenue, top-selling products and low-stock alerts. Data visualization supports charts and summary widgets.

  **● Manage Employees:** Users can send invitations to other users to join the management of that business location as an employee. Users can also remove an employee from the business location.

  **Administrator:**

  **● Manage Accounts:** Admins can view, search, filter, and manage all user accounts. This includes activating or deactivating accounts and viewing detailed profiles.

  **● Manage Subscription Pricing:** Admins can define and update the pricing for the subscription plan offered on the platform.

  **● Platform Analytics & Reporting:** Admins can access a global dashboard to monitor the revenue of the entire platform. This includes viewing total active accounts.

  **● System Configuration and Manage Financial Templates:** Admins can manage global system settings. Updating the master templates for financial reports (Circular 152/2025/TT-BTC) and broadcasting system-wide announcements.

  **● Manage notifications:** Manage notifications for the platform.

  **Consultant:**

    **● Manage Financial Templates:** Updating the master templates for financial reports (Circular 152/2025/TT-BTC).

  **● Manage notifications:** Create notifications for user about updating template reports and critical regulatory changes (e.g., tax circulars).

  **System:**

  **● Convert natural language into draft order:** It "listens" (or reads) to what the user says (e.g., "get 5 cement bags for Mr. Ba, put it on his tab") and automatically creates a draft order from that command.

  **●Automated simplified bookkeeping support:** The platform records daily transactions and generates draft simplified accounting books and summary reports in accordance with Circular 152/2025/TT-BTC, enabling household business owners to review and submit tax self-declaration records accurately without manual calculations or Excel-based bookkeeping.

  **● Revenue forecast**: The system can predict revenue in the near future based on past revenue.

  **● Warning of unusual data**: The system will issue alerts for unusual data from business operations.

  ● **Non-functional requirements**:  

  **1\. Security & Privacy**

  ● Supports the storage of sales data for at least 5 years.

  ● Strict role-based access control for User, Consultant and Admin roles.

  **2\. Performance & Scalability**

  ● Application responds quickly (\< 2000 ms for core actions).

  ● Supports large product catalogs and multiple concurrent users.

  **3\. Reliability & AI Accuracy**

  ● User can review, edit, or reject AI-generated draft orders.

  ● Fall back to manual operation if AI is unavailable.

  **4\. Usability & Accessibility**

  ● Simple, responsive web/mobile UI suitable for low digital literacy.

  ● Vietnamese interface; Unicode preserved.

  ● Real-time notifications.

**5\. Compliance & Reporting**

  ● Support generates accounting reports following Circular 152/2025/TT-BTC.

● The platform guarantees that all accounting report templates will be continuously updated to align with any future changes in the official declaration forms issued by the tax authorities.

(\*) **3.2. Main Proposal Content (including result and product)** 

**a. Theory and Practice (Document):** 

● Students should apply the software development process and UML 2.0 to model the system.

● The documentation includes: 

    ○ User Requirement

    ○ Software Requirement Specification

    ○ Architecture Design

    ○ Detailed Design

    ○ System Implementation

    ○ Testing Document

    ○ Installation Guide
    
    ○ Source code and deployable software packages

● **Server-side technologies:**

    ○ Clean architecture implemented in **ASP.NET Core**

    ○ Data storage with **MySQL**

● **AI:** Python

    **○** RAG: **ChromaDB, multilingual e5 large**

    **○** LLM: **OpenAI/Gemini**

    **○** Speech-to-Text: **Google Speech-to-Text/Whisper**

● **Client-side technologies:**

    ○ Mobile application: **Flutter.**  
    ○ Web Client: **ReactJS.**

    **b. Products:** 

● Mobile application 

● Web application 

**c. Proposed Tasks:** 
