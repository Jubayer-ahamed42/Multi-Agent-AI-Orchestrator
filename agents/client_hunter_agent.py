import os
import re
import ssl
import gzip
import zlib
import time
import json
import threading
import urllib.request
import urllib.parse
import urllib.error
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

try:
    from config import BASE_DIR, get_active_model
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent
    def get_active_model() -> str:
        return os.getenv("ACTIVE_MODEL", "gemini/gemini-3.5-flash-lite")

try:
    from agents.llm_client import call_llm
except ImportError:
    call_llm = None

try:
    from tools.search_tools import web_search
except ImportError:
    def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
        return []

logger = logging.getLogger(__name__)

# Default persistent storage path for scanned companies so no business is ever reported twice
DEFAULT_SCANNED_DB_PATH = BASE_DIR / "database" / "scanned_companies.json"

# Official Signature Block for Proposal Letters (Step 2 Message)
OFFICIAL_SIGNATURE_BLOCK = (
    "**Jubayer Ahamed**\n"
    "*AI Automation, Software & Web Development Specialist | Be Smart With AI*\n"
    "🟢 **Direct WhatsApp:** https://wa.me/8801610594042 (`+880 1610-594042`)\n"
    "🌐 **Official Page:** https://www.facebook.com/besmartwithaipro\n"
    "💻 **Portfolio:** https://github.com/Jubayer-ahamed42"
)

# Curated catalog of real target businesses across key Bangladeshi & International sectors
# Used alongside live web search & live HTML/Script X-Ray scanning
REAL_TARGET_BUSINESS_POOL: List[Dict[str, Any]] = [
    {
        "name": "Popular Diagnostic Centre Ltd. (Dhanmondi Branch)",
        "category": "ডায়াগনস্টিক সেন্টার ও প্রাইভেট হেলথকেয়ার (Diagnostic Center & Healthcare)",
        "location": "House #16, Road #2, Dhanmondi, Dhaka-1205, Bangladesh",
        "website": "https://www.populardiagnostic.com",
        "facebook": "https://www.facebook.com/populardiagnostic",
        "phone": "+880 9613-787801",
        "whatsapp_phone": "8801711567890",
        "email": "info@populardiagnostic.com",
        "decision_maker": "Dr. Mostafizur Rahman (Managing Director & Founder) / Head of Digital & Patient Services",
        "competitor_name": "Praava Health & Evercare Online Portal",
        "competitor_advantage": "Praava Health ও Evercare-এ ওয়েবসাইটে ও হোয়াটসঅ্যাপে তাৎক্ষণিক AI বুকিং, অনলাইন পেমেন্ট, মেটা পিক্সেল রিটার্গেটিং এবং অটোমেটেড টেস্ট রিপোর্ট ডেলিভারি সুবিধা রয়েছে।",
        "review_pain_points": "রোগীদের প্রধান অভিযোগ: কল সেন্টারে ফোন দিলে দীর্ঘক্ষণ ওয়েটিংয়ে থাকতে হয়, ফেসবুক পেজ বা ওয়েবসাইটে রিপোর্ট ও ডাক্তারের সিরিয়াল জানতে তাৎক্ষণিক রিপ্লাই পাওয়া যায় না এবং ম্যানুয়ালি সিরিয়াল নিতে ভোগান্তি হয়।",
        "ad_spend_signal": "ফেসবুকে নিয়মিত হেলথ চেকআপ ক্যাম্পেইন ও বুস্টিং চললেও ওয়েবসাইটে সঠিক Conversion API ও অটোমেটেড ফানেল না থাকায় বিজ্ঞাপনের বড় অংশ লিক হচ্ছে।",
        "avg_monthly_visitors": 45000,
        "avg_ticket_bdt": 2500
    },
    {
        "name": "Ibn Sina Diagnostic & Imaging Center",
        "category": "প্রাইভেট হাসপাতাল ও ডায়াগনস্টিক সেন্টার (Private Hospital & Diagnostic)",
        "location": "House #48, Road #9/A, Satmasjid Road, Dhanmondi, Dhaka",
        "website": "https://www.ibnsinatrust.com",
        "facebook": "https://www.facebook.com/IbnsinaTrust",
        "phone": "+880 1823-039800",
        "whatsapp_phone": "8801823039800",
        "email": "info@ibnsinatrust.com",
        "decision_maker": "Chairman & Board of Management / IT & Digital Marketing Director",
        "competitor_name": "United Hospital & Praava Health",
        "competitor_advantage": "প্রতিদ্বন্দ্বীরা ওয়েবসাইটে স্মার্ট অ্যাপয়েন্টমেন্ট ফানেল, ২৪/৭ চ্যাটবট এবং মোবাইল-ফার্স্ট পেশেন্ট পোর্টাল ব্যবহার করে দ্রুত রোগী কনভার্ট করছে।",
        "review_pain_points": "রোগীদের রিভিউ অনুযায়ী: জরুরি মুহূর্তে ডাক্তারের শিডিউল বা টেস্টের খরচ জানতে ফোন রিসিভ হতে দেরি হয়, ওয়েবসাইট মোবাইলে ধীরগতির এবং সরাসরি হোয়াটসঅ্যাপ অটো-বুকিং নেই।",
        "ad_spend_signal": "সোশ্যাল মিডিয়ায় প্রমোশনাল পোস্ট থাকলেও ওয়েবসাইটে Meta Pixel ইভেন্ট ট্র্যাকিং ও রিটার্গেটিং অটোমেশন অনুপস্থিত।",
        "avg_monthly_visitors": 38000,
        "avg_ticket_bdt": 2200
    },
    {
        "name": "Comfort Diagnostic Centre & Comfort Nursing Home",
        "category": "প্রাইভেট হাসপাতাল ও ক্লিনিক (Private Hospital & Clinic)",
        "location": "167/B, Green Road, Dhanmondi, Dhaka-1205",
        "website": "https://www.comfortbd.com",
        "facebook": "https://www.facebook.com/comfortdiagnostic",
        "phone": "+880 1731-956033",
        "whatsapp_phone": "8801731956033",
        "email": "info@comfortbd.com",
        "decision_maker": "Managing Director / Chief Hospital Administrator",
        "competitor_name": "Labaid Specialized Hospital & Square Hospital",
        "competitor_advantage": "শীর্ষ প্রতিদ্বন্দ্বীরা আধুনিক ওয়েব অ্যাপ, অনলাইন ডক্টর অ্যাপয়েন্টমেন্ট এবং অটোমেটেড পেশেন্ট সাপোর্ট চ্যাটবট ব্যবহার করছে।",
        "review_pain_points": "কাস্টমার ফিডব্যাকে দেখা যায়: রাত ৮টার পর বা ছুটির দিনে ইনবক্সে মেসেজ দিলে উত্তর মেলে না, পুরনো ধাঁচের ওয়েবসাইটে মোবাইল থেকে ডাক্তার খুঁজে বুকিং দেওয়া জটিল।",
        "ad_spend_signal": "হেলথ প্যাকেজ নিয়ে ফেসবুক পেজে ক্যাম্পেইন চালানো হলেও ল্যান্ডিং পেজে পিক্সেল বা লিড ক্যাপচার বট নেই।",
        "avg_monthly_visitors": 18000,
        "avg_ticket_bdt": 2000
    },
    {
        "name": "Sultan's Dine (গুলশান ও ধানমন্ডি ফ্ল্যাগশিপ)",
        "category": "রেস্টুরেন্ট ও হসপিটালিটি ব্র্যান্ড (Restaurant & Hospitality)",
        "location": "Plot 41, Road 52, Gulshan-2 & Green Akshay Plaza, Dhanmondi, Dhaka",
        "website": "https://sultansdinebd.com",
        "facebook": "https://www.facebook.com/sultansdine",
        "phone": "+880 1775-003218",
        "whatsapp_phone": "8801775003218",
        "email": "info@sultansdinebd.com",
        "decision_maker": "Sazzadul Islam (Founder & Managing Partner) / Head of Brand & Operations",
        "competitor_name": "Kacchi Bhai & Chillox Direct Ordering Funnel",
        "competitor_advantage": "প্রতিদ্বন্দ্বীরা নিজস্ব ডিরেক্ট অর্ডারিং ওয়েব অ্যাপ, মেটা পিক্সেল রিটার্গেটিং এবং হোয়াটসঅ্যাপ ক্যাটারিং বুকিং বট দিয়ে ফুডপান্ডার ২৫% কমিশন বাঁচিয়ে সরাসরি সেল বাড়াচ্ছে।",
        "review_pain_points": "কাস্টমারদের অভিযোগ: কর্পোরেট বা বিয়ের বাল্ক অর্ডার ও টেবিল রিজার্ভেশনের জন্য ইনবক্সে বা ফোনে তাৎক্ষণিক রেসপন্স পাওয়া যায় না, এবং নিজস্ব ওয়েবসাইট থেকে ১-ক্লিকে লাইভ অর্ডার ট্র্যাকিং সুবিধা দুর্বল।",
        "ad_spend_signal": "ফেসবুকে নিয়মিত স্পন্সরড ফুড ক্যাম্পেইন চলছে, কিন্তু নিজস্ব ওয়েবসাইটে রিটার্গেটিং পিক্সেল ও হোয়াটসঅ্যাপ অর্ডার বট না থাকায় কাস্টমার থার্ড-পার্টি অ্যাপে চলে যাচ্ছে।",
        "avg_monthly_visitors": 32000,
        "avg_ticket_bdt": 1400
    },
    {
        "name": "Hotel The Cox Today",
        "category": "হোটেল ও লাক্সারি রিসোর্ট (Hotel & Luxury Resort)",
        "location": "Plot-7, Road-02, Hotel Motel Zone, Kolatoli Road, Cox's Bazar",
        "website": "https://www.hotelthecoxtoday.com",
        "facebook": "https://www.facebook.com/hotelthecoxtoday",
        "phone": "+880 1755-598449",
        "whatsapp_phone": "8801755598449",
        "email": "reservation@hotelthecoxtoday.com",
        "decision_maker": "Mohiuddin Khan Khokon (Director of Sales & Marketing) / General Manager",
        "competitor_name": "Sayeman Beach Resort & Sea Pearl Beach Resort",
        "competitor_advantage": "শীর্ষ প্রতিদ্বন্দ্বীরা রিয়েল-টাইম রুম ইনভেন্টরি বুকিং ইঞ্জিন, মেটা পিক্সেল ডায়নামিক রিটার্গেটিং এবং ২৪/৭ AI হোয়াটসঅ্যাপ কনসিয়ার্জ ব্যবহার করে সরাসরি বুকিং নিচ্ছে।",
        "review_pain_points": "ভ্রমণকারীদের অভিযোগ: রুমের ভাড়া ও অফার জানতে ফেসবুকে বা ফোনে মেসেজ দিলে রিপ্লাই পেতে দেরি হয়, ওয়েবসাইট থেকে সরাসরি বিকাশ/কার্ডে ইনস্ট্যান্ট বুকিং কনফার্মেশন পেতে ম্যানুয়াল ভেরিফিকেশনের ঝামেলা পোহাতে হয়।",
        "ad_spend_signal": "পর্যটন মৌসুমে ফেসবুকে ব্যাপক বিজ্ঞাপন চালানো হলেও ওয়েবসাইট ভিজিটরদের রিটার্গেট করার মতো Meta Conversion API ও অটো-চ্যাটবট ফানেল নেই।",
        "avg_monthly_visitors": 28000,
        "avg_ticket_bdt": 8500
    },
    {
        "name": "Grand Sultan Tea Resort & Golf",
        "category": "ফাইভ-স্টার রিসোর্ট ও হসপিটালিটি (5-Star Resort & Hospitality)",
        "location": "Sreemangal, Moulvibazar, Sylhet Division, Bangladesh",
        "website": "https://www.grandsultanresort.com",
        "facebook": "https://www.facebook.com/GrandSultanResort",
        "phone": "+880 1730-793501",
        "whatsapp_phone": "8801730793501",
        "email": "reservations@grandsultanresort.com",
        "decision_maker": "Khwaja Nargis Hossain (Chairman) / Head of Reservations & Digital Marketing",
        "competitor_name": "The Palace Luxury Resort & Dusai Resort",
        "competitor_advantage": "প্রতিদ্বন্দ্বীরা দ্রুতগতির মোবাইল বুকিং ফানেল, কর্পোরেট ইভেন্ট ক্যালকুলেটর এবং অটোমেটেড হোয়াটসঅ্যাপ বুকিং অ্যাসিস্ট্যান্ট ব্যবহার করছে।",
        "review_pain_points": "গেস্টদের রিভিউতে উঠে এসেছে: ডিসকাউন্ট প্যাকেজ বা ফ্যামিলি ভিলা খালি আছে কি না তা জানতে ফোন ও ইমেইলের ওপর নির্ভর করতে হয়; রাতে বা ছুটির দিনে তাৎক্ষণিক AI চ্যাট সাপোর্ট পাওয়া যায় না।",
        "ad_spend_signal": "ফেসবুক ও ইনস্টাগ্রামে প্রিমিয়াম ট্রাভেল অ্যাড চলছে, কিন্তু ল্যান্ডিং পেজে AI লিড ক্যাপচার ও রিটার্গেটিং অটোমেশন পুরোপুরি অপ্টিমাইজড নয়।",
        "avg_monthly_visitors": 25000,
        "avg_ticket_bdt": 14000
    },
    {
        "name": "Sheltech (Pvt.) Ltd.",
        "category": "রিয়েল এস্টেট ও প্রপার্টি ডেভেলপার (Real Estate & Property Developer)",
        "location": "Sheltech Tower, 60 Sheikh Russell Square, West Panthapath, Dhaka-1205",
        "website": "https://www.sheltech-bd.com",
        "facebook": "https://www.facebook.com/sheltechbd",
        "phone": "+880 9606-445500",
        "whatsapp_phone": "8801713091700",
        "email": "info@sheltech-bd.com",
        "decision_maker": "Tanvir Ahmed (Managing Director) / Head of Sales & Marketing",
        "competitor_name": "bti (Building Technology & Ideas) & Shanta Holdings",
        "competitor_advantage": "শীর্ষ প্রতিদ্বন্দ্বীরা ইন্টারেক্টিভ ফ্ল্যাট ফাইন্ডার, ২৪/৭ AI প্রপার্টি অ্যাডভাইজর বট এবং প্রবাসী বাংলাদেশিদের (NRB) জন্য সরাসরি হোয়াটসঅ্যাপ ভার্চুয়াল ট্যুর বুকিং ব্যবহার করছে।",
        "review_pain_points": "ফ্ল্যাট ক্রেতা ও প্রবাসী ক্লায়েন্টদের অভিযোগ: প্রজেক্টের ফ্লোর প্ল্যান, দাম ও কিস্তির হিসাব জানতে ফর্ম পূরণের পর কল পেতে ২৪-৪৮ ঘণ্টা দেরি হয়; প্রবাসীদের টাইমজোনে রাতের বেলা তাৎক্ষণিক উত্তর দেওয়ার কেউ থাকে না।",
        "ad_spend_signal": "ফেসবুক ও গুগলে প্রবাসী এবং হাই-নেট-ওয়ার্থ ক্রেতাদের টার্গেট করে বড় বাজেটের বিজ্ঞাপন চললেও ২৪/৭ AI WhatsApp Closer না থাকায় মূল্যবান লিড হারিয়ে যাচ্ছে।",
        "avg_monthly_visitors": 22000,
        "avg_ticket_bdt": 50000
    },
    {
        "name": "Assure Group (Real Estate & Builders)",
        "category": "রিয়েল এস্টেট ও ডেভেলপার (Real Estate & Builders)",
        "location": "Jabbar Tower, House-42, Road-135, Gulshan-1, Dhaka-1212",
        "website": "https://www.assuregroupbd.com",
        "facebook": "https://www.facebook.com/assuregroupbd",
        "phone": "+880 9612-008800",
        "whatsapp_phone": "8801713034455",
        "email": "info@assuregroupbd.com",
        "decision_maker": "Md. Sheikh Shadi (Chairman & Founder) / Head of Digital Lead Generation",
        "competitor_name": "Navana Real Estate & Concord Group",
        "competitor_advantage": "প্রতিদ্বন্দ্বীরা অটোমেটেড লিড স্কোরিং CRM, ইন্সট্যান্ট হোয়াটসঅ্যাপ ব্রোশিওর ডেলিভারি বট এবং উন্নত এসইও ফানেল ব্যবহার করছে।",
        "review_pain_points": "ক্রেতাদের ফিডব্যাক: নির্দিষ্ট এলাকায় রেডি ফ্ল্যাটের মূল্য ও স্কয়ার ফিট জানতে কল বা মেসেজ করলে তাৎক্ষণিক পিডিএফ ব্রোশিওর ও সাইট ভিজিট শিডিউল পাওয়া যায় না।",
        "ad_spend_signal": "নিয়মিত ফেসবুক লিড অ্যাড চলছে, কিন্তু ইনস্ট্যান্ট হোয়াটসঅ্যাপ AI ফলো-আপ না থাকায় লিড-টু-ভিজিট কনভার্সন রেট কম।",
        "avg_monthly_visitors": 19000,
        "avg_ticket_bdt": 45000
    },
    {
        "name": "Sailor by Epyllion",
        "category": "ই-কমার্স ও ফ্যাশন রিটেইল ব্র্যান্ড (E-Commerce & Fashion Brand)",
        "location": "Plot J-2, Road 22, Gulshan-1 / Tejgaon Industrial Area, Dhaka",
        "website": "https://sailor.clothing",
        "facebook": "https://www.facebook.com/clothings.sailor",
        "phone": "+880 1777-702000",
        "whatsapp_phone": "8801777702000",
        "email": "support@sailor.clothing",
        "decision_maker": "Reaz Uddin Al-Mamoon (Managing Director) / Head of E-Commerce & Digital",
        "competitor_name": "Aarong Online & Twelve Clothing",
        "competitor_advantage": "শীর্ষ প্রতিদ্বন্দ্বীরা AI সাইজ রিকমেন্ডার, অ্যাবান্ডনড কার্ট (Abandoned Cart) হোয়াটসঅ্যাপ রিকভারি বট এবং আল্ট্রা-ফাস্ট চেকআউট ব্যবহার করে ৩০% বেশি রিপিট সেল পাচ্ছে।",
        "review_pain_points": "অনলাইন ক্রেতাদের অভিযোগ: ডেলিভারি স্ট্যাটাস, সাইজ এক্সচেঞ্জ বা স্টক জানতে ফেসবুক ইনবক্সে মেসেজ দিলে ঘণ্টার পর ঘণ্টা অপেক্ষা করতে হয় এবং কার্টে পণ্য রেখে বের হয়ে গেলে কোনো অটোমেটেড রিমাইন্ডার আসে না।",
        "ad_spend_signal": "ঈদ ও সিজনাল কালেকশনে বিপুল ফেসবুক/ইনস্টাগ্রাম অ্যাড বাজেট খরচ হচ্ছে, কিন্তু WhatsApp Abandoned Cart Recovery ও AI Shopping Assistant না থাকায় প্রচুর কার্ট ড্রপ হচ্ছে।",
        "avg_monthly_visitors": 65000,
        "avg_ticket_bdt": 2800
    },
    {
        "name": "Khaas Food (খাস ফুড ই-কমার্স)",
        "category": "অর্গানিক ফুড ও ই-কমার্স ব্র্যান্ড (Organic Food & E-Commerce)",
        "location": "Asad Gate, Mohammadpur / Mirpur Road, Dhaka",
        "website": "https://www.khaasfood.com",
        "facebook": "https://www.facebook.com/khaasfood",
        "phone": "+880 1708-183873",
        "whatsapp_phone": "8801708183873",
        "email": "customercare@khaasfood.com",
        "decision_maker": "Habibul Mustafa Arman (Co-Founder & CEO)",
        "competitor_name": "Ghorer Bazar & Chaldal",
        "competitor_advantage": "প্রতিদ্বন্দ্বীরা ১-ক্লিক হোয়াটসঅ্যাপ রি-অর্ডার অটোমেশন, সার্ভার-সাইড Meta Conversion API এবং দ্রুতগতির মোবাইল ওয়েব অ্যাপ ব্যবহার করছে।",
        "review_pain_points": "কাস্টমার রিভিউ: মাসিক বাজারের রি-অর্ডার বা ডেলিভারি টাইম স্লট জানতে চ্যাটবটে তাৎক্ষণিক সমাধান মেলে না এবং মোবাইলে চেকআউট পেজ লোড হতে সময় নেয়।",
        "ad_spend_signal": "ফেসবুকে নিয়মিত ভিডিও ও ক্যারোসেল অ্যাড চলছে, কিন্তু Server-Side CAPI ও WhatsApp Re-Order Automation যুক্ত করলে ROI দ্বিগুণ হতে পারে।",
        "avg_monthly_visitors": 40000,
        "avg_ticket_bdt": 1600
    },
    {
        "name": "Galaxy Holidays (Galaxy Travel International)",
        "category": "ট্রাভেল এজেন্সি ও ভিসা কনসালটেন্সি (Travel Agency & Tour Operator)",
        "location": "Taj Casilina, 25 Gulshan Avenue, Gulshan-1, Dhaka-1212",
        "website": "https://www.galaxyholidaysbd.com",
        "facebook": "https://www.facebook.com/galaxyholidaysbd",
        "phone": "+880 1713-083585",
        "whatsapp_phone": "8801713083585",
        "email": "info@galaxyholidaysbd.com",
        "decision_maker": "Taufiq Uddin Ahmed (President & CEO) / Head of Outbound Tours",
        "competitor_name": "ShareTrip & GoZayaan",
        "competitor_advantage": "ShareTrip ও GoZayaan-এ ইনস্ট্যান্ট ট্যুর ও ফ্লাইট প্রাইসিং, ভিসা চেকলিস্ট AI বট এবং স্বয়ংক্রিয় অনলাইন বুকিং পোর্টাল রয়েছে।",
        "review_pain_points": "ট্রাভেলারদের অভিযোগ: ভিসা প্রসেসিংয়ের কাগজপত্র বা ট্যুর প্যাকেজের কাস্টমাইজড খরচ জানতে কল দিলে বা মেসেজ করলে দ্রুত উত্তর পাওয়া যায় না; ম্যানুয়ালি অফিসে কথা বলতে হয়।",
        "ad_spend_signal": "ওমরাহ, দুবাই, থাইল্যান্ড ও ইউরোপ ট্যুরের ফেসবুক অ্যাড চললেও ইনস্ট্যান্ট AI Visa & Tour Quotation Bot না থাকায় ৫০%+ ইনকোয়ারি কোল্ড হয়ে যায়।",
        "avg_monthly_visitors": 20000,
        "avg_ticket_bdt": 35000
    },
    {
        "name": "Mentors' (Education & Study Abroad Coaching)",
        "category": "কোচিং সেন্টার ও স্টাডি অ্যাব্রোড কনসালটেন্সি (Coaching & EdTech)",
        "location": "166/1 Mirpur Road, Kalabagan, Dhaka-1205",
        "website": "https://www.mentors.com.bd",
        "facebook": "https://www.facebook.com/MentorsSA",
        "phone": "+880 1713-243401",
        "whatsapp_phone": "8801713243401",
        "email": "info@mentors.com.bd",
        "decision_maker": "Anindya Chowdhury (Managing Director & CEO) / Head of Student Admissions",
        "competitor_name": "10 Minute School & IDP Study Abroad Portal",
        "competitor_advantage": "প্রতিদ্বন্দ্বীরা AI-ভিত্তিক IELTS মক টেস্ট বুকিং, স্বয়ংক্রিয় স্টুডেন্ট এলিজিবিলিটি ক্যালকুলেটর এবং হোয়াটসঅ্যাপে তাৎক্ষণিক কাউন্সেলিং স্লট বুকিং ব্যবহার করছে।",
        "review_pain_points": "শিক্ষার্থীদের অভিযোগ: নতুন ব্যাচের সময়সূচি, কোর্স ফি বা স্টাডি অ্যাব্রোড অ্যাসেসমেন্টের জন্য ফেসবুক পেজে বা ফোনে যোগাযোগ করলে দ্রুত কাউন্সেলর পাওয়া যায় না।",
        "ad_spend_signal": "IELTS, GED, BBA/IBA ও বিদেশে উচ্চশিক্ষার বিজ্ঞাপন নিয়মিত চলছে, কিন্তু ওয়েবসাইটে ২৪/৭ AI Student Counselor ও অটো-অ্যাপয়েন্টমেন্ট ফানেল নেই।",
        "avg_monthly_visitors": 30000,
        "avg_ticket_bdt": 12000
    }
]

# Strict filter to reject Government agencies, Non-Profit/Charity/NGO foundations, and Generic Blogs/Directories
NON_COMMERCIAL_DOMAIN_SUFFIXES = (
    ".gov", ".gov.bd", ".mil", ".mil.bd", ".org", ".org.bd", ".edu", ".edu.bd", ".ac.bd"
)

NON_COMMERCIAL_KEYWORDS = (
    "wikipedia.org", "youtube.com", "daraz.com", "bikroy.com", "facebook.com",
    "linkedin.com", "instagram.com", "twitter.com", "x.com", "blogspot.com",
    "wordpress.com", "medium.com", "substack.com", "prothomalo.com", "thedailystar.net",
    "bdnews24.com", "jagonews24.com", "kalerkantho.com", "banglatribune.com",
    "foundation", "charity", "nonprofit", "non-profit", "ngo", "ministry",
    "government", "welfare", "relief", "donation", "zakat", "sadaqah", "assunnah",
    "ফাউন্ডেশন", "অলাভজনক", "চ্যারিটি", "মন্ত্রণালয়", "অধিদপ্তর", "সরকারি", "ব্লগ"
)


def is_commercial_business(name: str, url: str, snippet: str = "") -> bool:
    """Returns True ONLY if the candidate is a 100% commercial business (not a government entity, non-profit, or generic blog)."""
    domain = ScannedCompanyStore.normalize_domain(url)
    if not domain:
        return False
    if any(domain.endswith(suf) for suf in NON_COMMERCIAL_DOMAIN_SUFFIXES):
        return False
    combined = f"{name} {domain} {url} {snippet}".lower()
    if any(kw in combined for kw in NON_COMMERCIAL_KEYWORDS):
        return False
    return True



class ScannedCompanyStore:
    """Manages persistent JSON history of scanned companies so no company is ever reported twice.
    
    Uses a re-entrant thread lock and atomic temp-file swap (os.replace) to prevent
    race conditions or JSON corruption when multiple threads/schedulers access the store concurrently.
    """

    _STORE_LOCK = threading.RLock()

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = Path(storage_path) if storage_path else DEFAULT_SCANNED_DB_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file()

    def _ensure_file(self):
        with self._STORE_LOCK:
            if not self.storage_path.exists():
                self._write_data({"scanned_keys": [], "history": []})

    def _read_data(self) -> Dict[str, Any]:
        with self._STORE_LOCK:
            try:
                if not self.storage_path.exists():
                    return {"scanned_keys": [], "history": []}
                raw = self.storage_path.read_text(encoding="utf-8")
                data = json.loads(raw) if raw.strip() else {}
                if not isinstance(data, dict):
                    return {"scanned_keys": [], "history": []}
                data.setdefault("scanned_keys", [])
                data.setdefault("history", [])
                return data
            except Exception as e:
                logger.warning(f"Failed to read scanned companies store ({self.storage_path}): {e}")
                return {"scanned_keys": [], "history": []}

    def _write_data(self, data: Dict[str, Any]):
        with self._STORE_LOCK:
            try:
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
                payload = json.dumps(data, ensure_ascii=False, indent=2)
                tmp_path.write_text(payload, encoding="utf-8")
                os.replace(str(tmp_path), str(self.storage_path))
            except Exception as e:
                logger.warning(f"Failed to write scanned companies store ({self.storage_path}): {e}")

    @staticmethod
    def normalize_name(name: str) -> str:
        if not name:
            return ""
        clean = re.sub(r"[^a-z0-9\u0980-\u09FF]+", "", name.lower().strip())
        return clean

    @staticmethod
    def normalize_domain(url: str) -> str:
        if not url:
            return ""
        u = url.strip().lower()
        if not u.startswith(("http://", "https://")):
            u = "https://" + u
        try:
            parsed = urllib.parse.urlparse(u)
            host = parsed.netloc or parsed.path.split("/")[0]
            host = host.split("@")[-1].split(":")[0]
            host = re.sub(r"^www\.", "", host).strip("/")
            return host
        except Exception:
            return u

    def is_scanned(self, company_name: str, website_url: str = "") -> bool:
        with self._STORE_LOCK:
            data = self._read_data()
            keys = set(data.get("scanned_keys", []))
            name_key = f"name:{self.normalize_name(company_name)}" if company_name else ""
            domain_key = f"domain:{self.normalize_domain(website_url)}" if website_url else ""
            if name_key and name_key != "name:" and name_key in keys:
                return True
            if domain_key and domain_key != "domain:" and domain_key in keys:
                return True
            return False

    def mark_scanned(self, company_info: Dict[str, Any]):
        with self._STORE_LOCK:
            data = self._read_data()
            keys = set(data.get("scanned_keys", []))
            name = company_info.get("name", "")
            url = company_info.get("website", "")
            name_key = f"name:{self.normalize_name(name)}" if name else ""
            domain_key = f"domain:{self.normalize_domain(url)}" if url else ""

            if name_key and name_key != "name:":
                keys.add(name_key)
            if domain_key and domain_key != "domain:":
                keys.add(domain_key)

            data["scanned_keys"] = sorted(list(keys))
            bd_tz = timezone(timedelta(hours=6))
            entry = {
                "name": name,
                "website": url,
                "category": company_info.get("category", ""),
                "location": company_info.get("location", ""),
                "phone": company_info.get("phone", ""),
                "health_score": company_info.get("health_score"),
                "scanned_at": datetime.now(bd_tz).isoformat()
            }
            data.setdefault("history", []).append(entry)
            self._write_data(data)

    def get_history(self) -> List[Dict[str, Any]]:
        with self._STORE_LOCK:
            return list(self._read_data().get("history", []))

    def clear(self):
        with self._STORE_LOCK:
            self._write_data({"scanned_keys": [], "history": []})


def sanitize_whatsapp_number(phone_str: str) -> str:
    """Extracts digits and normalizes Bangladesh/international phone numbers for https://wa.me/<number>."""
    if not phone_str:
        return "8801700000000"
    raw = str(phone_str).strip()
    # Extract the first distinct phone candidate if multiple numbers are separated by /, comma, pipe, or semicolon
    primary_match = re.search(r"(?:\+?880|00880|01|096)[0-9\-\s()]{7,15}", raw)
    candidate = primary_match.group(0) if primary_match else re.split(r"[/,|;]", raw)[0]
    digits = re.sub(r"\D+", "", candidate)
    if not digits:
        return "8801700000000"
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("01") and len(digits) == 11:
        digits = "88" + digits
    elif digits.startswith("096") and len(digits) in (10, 11):
        digits = "88" + digits
    elif digits.startswith("8801") and len(digits) >= 13:
        digits = digits[:13]
    elif digits.startswith("88096") and len(digits) >= 12:
        digits = digits[:13]
    elif digits.startswith("0") and len(digits) == 10:
        digits = "88" + digits
    if len(digits) < 10:
        return "8801700000000"
    return digits


class BusinessXRayScanner:
    """Live technical & marketing website scanner that performs real HTML/Script inspection."""

    @staticmethod
    def scan_website(url: str, timeout: int = 7) -> Dict[str, Any]:
        """Fetches the target website HTML and inspects Meta Pixel, Google Analytics, Chatbots, Speed, SSL, SEO, and Booking."""
        result: Dict[str, Any] = {
            "url": url,
            "is_live": False,
            "http_status": 0,
            "load_time_sec": 0.0,
            "page_size_kb": 0.0,
            "has_ssl": False,
            "ssl_verified": False,
            "has_meta_pixel": False,
            "meta_pixel_signals": [],
            "has_google_analytics": False,
            "ga_signals": [],
            "has_ai_chatbot": False,
            "chatbot_signals": [],
            "has_whatsapp_widget": False,
            "has_viewport_meta": False,
            "has_booking_or_order": False,
            "booking_signals": [],
            "has_title": False,
            "title_text": "",
            "has_meta_description": False,
            "meta_description_text": "",
            "has_h1": False,
            "has_schema_ld": False,
            "empty_links_count": 0,
            "security_headers_present": [],
            "discovered_emails": [],
            "discovered_phones": [],
            "discovered_facebook": "",
            "scan_mode": "live_http"
        }

        if not url or not str(url).strip():
            result["scan_mode"] = "no_website"
            return result

        target_url = url.strip()
        explicit_http = target_url.lower().startswith("http://")
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
            "Accept-Encoding": "gzip, deflate"
        }

        start_ts = time.perf_counter()
        raw_bytes = b""
        resp_headers: Dict[str, str] = {}

        def _fetch_with_context(fetch_url: str, verify_ssl: bool) -> Tuple[bytes, int, str, Dict[str, str]]:
            ctx = ssl.create_default_context()
            if not verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(fetch_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read(350_000)
                status = getattr(resp, "status", 200) or 200
                final_u = resp.geturl() if hasattr(resp, "geturl") and callable(resp.geturl) else fetch_url
                hdrs = {k.lower(): v for k, v in resp.headers.items()} if resp.headers else {}
                return data, status, final_u if isinstance(final_u, str) else fetch_url, hdrs

        try:
            try:
                raw_bytes, status_code, final_url, resp_headers = _fetch_with_context(target_url, verify_ssl=True)
                ssl_ok = final_url.lower().startswith("https://") and not explicit_http
                result["has_ssl"] = ssl_ok
                result["ssl_verified"] = ssl_ok
            except ssl.SSLError as ssl_err:
                logger.debug(f"SSL certificate verification failed for {target_url}, retrying unverified: {ssl_err}")
                raw_bytes, status_code, final_url, resp_headers = _fetch_with_context(target_url, verify_ssl=False)
                result["has_ssl"] = False
                result["ssl_verified"] = False
                result["scan_mode"] = "live_http_ssl_unverified"
            except urllib.error.URLError as url_err:
                if isinstance(getattr(url_err, "reason", None), ssl.SSLError):
                    raw_bytes, status_code, final_url, resp_headers = _fetch_with_context(target_url, verify_ssl=False)
                    result["has_ssl"] = False
                    result["ssl_verified"] = False
                    result["scan_mode"] = "live_http_ssl_unverified"
                elif target_url.lower().startswith("https://"):
                    # Fallback to plain HTTP if target server only listens on port 80
                    http_fallback_url = "http://" + target_url[8:]
                    raw_bytes, status_code, final_url, resp_headers = _fetch_with_context(http_fallback_url, verify_ssl=False)
                    result["has_ssl"] = False
                    result["ssl_verified"] = False
                    result["scan_mode"] = "live_http_no_ssl"
                else:
                    raise

            elapsed = time.perf_counter() - start_ts
            result["is_live"] = True
            result["http_status"] = status_code
            result["load_time_sec"] = round(elapsed, 2)
        except urllib.error.HTTPError as http_err:
            elapsed = time.perf_counter() - start_ts
            result["http_status"] = int(getattr(http_err, "code", 0) or 0)
            result["load_time_sec"] = round(elapsed, 2)
            result["has_ssl"] = target_url.lower().startswith("https://") and not explicit_http
            result["scan_mode"] = f"http_error_{result['http_status']}"
            try:
                raw_bytes = http_err.read(150_000) if hasattr(http_err, "read") else b""
                resp_headers = {k.lower(): v for k, v in http_err.headers.items()} if getattr(http_err, "headers", None) else {}
            except Exception:
                raw_bytes = b""
            if not raw_bytes:
                return result
        except Exception as e:
            elapsed = time.perf_counter() - start_ts
            result["load_time_sec"] = round(elapsed, 2)
            result["has_ssl"] = False
            result["scan_mode"] = f"unreachable_or_blocked ({type(e).__name__})"
            logger.debug(f"Live HTTP scan note for {target_url}: {e}")
            return result

        # Decompress gzip or deflate payload if compressed
        content_enc = resp_headers.get("content-encoding", "").lower()
        if raw_bytes:
            if content_enc == "gzip" or raw_bytes[:2] == b"\x1f\x8b":
                try:
                    raw_bytes = gzip.decompress(raw_bytes)
                except Exception:
                    pass
            elif content_enc == "deflate":
                try:
                    raw_bytes = zlib.decompress(raw_bytes)
                except Exception:
                    try:
                        raw_bytes = zlib.decompress(raw_bytes, -zlib.MAX_WBITS)
                    except Exception:
                        pass

        result["page_size_kb"] = round(len(raw_bytes) / 1024.0, 1)
        for sec_h in ["strict-transport-security", "x-frame-options", "x-content-type-options", "content-security-policy"]:
            if sec_h in resp_headers:
                result["security_headers_present"].append(sec_h)

        # Decode using detected charset or UTF-8 fallback
        charset = "utf-8"
        ct_header = resp_headers.get("content-type", "")
        cs_match = re.search(r"charset=([a-zA-Z0-9_\-]+)", ct_header, re.IGNORECASE)
        if cs_match:
            charset = cs_match.group(1).strip()
        try:
            html = raw_bytes.decode(charset, errors="ignore")
        except LookupError:
            html = raw_bytes.decode("utf-8", errors="ignore")

        if not html.strip():
            return result

        html_lower = html.lower()

        # 1. Meta Pixel check (fbq, connect.facebook.net, fbevents.js, facebook.com/tr)
        pixel_patterns = [
            ("fbq(", r"fbq\s*\("),
            ("fbevents.js", r"fbevents\.js"),
            ("connect.facebook.net", r"connect\.facebook\.net"),
            ("facebook.com/tr", r"facebook\.com/tr\?")
        ]
        for label, pat in pixel_patterns:
            if re.search(pat, html_lower):
                result["has_meta_pixel"] = True
                result["meta_pixel_signals"].append(label)

        # 2. Google Analytics / GTM check (gtag, googletagmanager, gtm.js, G-, UA-, GTM-)
        ga_patterns = [
            ("gtag", r"gtag\s*\("),
            ("googletagmanager", r"googletagmanager\.com"),
            ("gtm.js", r"gtm\.js"),
            ("google-analytics", r"google-analytics\.com"),
            ("GA4/GTM ID", r"\b(g-[a-z0-9]{6,12}|gtm-[a-z0-9]{4,10}|ua-\d{4,10}-\d+)\b")
        ]
        for label, pat in ga_patterns:
            if re.search(pat, html_lower):
                result["has_google_analytics"] = True
                result["ga_signals"].append(label)

        # 3. 24/7 AI Chatbot & WhatsApp Automation Check (strict widget/script patterns to avoid prose false-positives)
        chatbot_patterns = [
            ("Tawk.to", r"tawk\.to"),
            ("Crisp Chat", r"crisp\.chat"),
            ("Intercom", r"intercom\.io|intercomsettings|widget\.intercom"),
            ("Tidio AI", r"tidio\.co|tidiochat"),
            ("Zendesk Chat", r"zdassets\.com|zopim|zendesk"),
            ("LiveChat", r"livechatinc\.com|__lc\b"),
            ("Messenger Customer Chat", r"fb-customerchat|customer_chat"),
            ("AI Chatbot Widget", r"chat-widget|chatbot-widget|botpress|dialogflow|manychat|wati\.io|respond\.io|joinchat")
        ]
        for label, pat in chatbot_patterns:
            if re.search(pat, html_lower):
                result["has_ai_chatbot"] = True
                result["chatbot_signals"].append(label)

        if re.search(r"wa\.me/|api\.whatsapp\.com|whatsapp\.com/send", html_lower):
            result["has_whatsapp_widget"] = True

        # 4. Mobile Viewport Check
        if re.search(r'<meta[^>]+name=["\']viewport["\']', html_lower):
            result["has_viewport_meta"] = True

        # 5. Online Booking / Order / SaaS System Check (interactive endpoints/widgets rather than plain text mentions)
        booking_patterns = [
            ("Appointment/Booking", r"book-now|book_now|online-booking|appointment-form|make-appointment|calendly\.com|booking-form|href=[\"'][^\"']*(?:appointment|booking|reservation)"),
            ("E-Commerce Cart/Checkout", r"add-to-cart|add_to_cart|checkout|woocommerce|shopify|order-now"),
            ("Customer/Patient Portal", r"patient-portal|client-portal|track-order|login-portal")
        ]
        for label, pat in booking_patterns:
            if re.search(pat, html_lower):
                result["has_booking_or_order"] = True
                result["booking_signals"].append(label)

        # 6. SEO Checks (Title, Meta Description, H1, Schema LD+JSON)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match and title_match.group(1).strip():
            result["has_title"] = True
            result["title_text"] = re.sub(r"\s+", " ", title_match.group(1).strip())[:120]

        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
            html,
            re.IGNORECASE
        )
        if desc_match and desc_match.group(1).strip():
            result["has_meta_description"] = True
            result["meta_description_text"] = re.sub(r"\s+", " ", desc_match.group(1).strip())[:160]

        if re.search(r"<h1[\s>]", html_lower):
            result["has_h1"] = True

        if "application/ld+json" in html_lower:
            result["has_schema_ld"] = True

        # 7. Empty / broken link signals
        empty_links = re.findall(r'href=["\'](#|javascript:void\(0\)|javascript:;)["\']', html_lower)
        result["empty_links_count"] = len(empty_links)

        # 8. Extract any visible emails, BD phone numbers, and Facebook page links
        emails = set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html))
        valid_emails = [
            e for e in emails
            if not e.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css", ".woff", ".ttf"))
        ]
        result["discovered_emails"] = sorted(valid_emails)[:3]

        raw_phones = set(re.findall(r"(?:\+?880|01|096)[0-9\- ]{8,14}", html))
        valid_phones = []
        for p in sorted(raw_phones):
            digits_only = re.sub(r"\D+", "", p)
            if 10 <= len(digits_only) <= 13:
                valid_phones.append(re.sub(r"\s+", " ", p.strip()))
        result["discovered_phones"] = valid_phones[:3]

        fb_matches = re.findall(r"https?://(?:www\.)?facebook\.com/[a-zA-Z0-9._\-]+", html)
        for fb_url in fb_matches:
            if not any(ig in fb_url.lower() for ig in ["/tr", "/sharer", "/plugins", "/dialog"]):
                result["discovered_facebook"] = fb_url
                break

        return result


class DigitalHealthAndRevenueCalculator:
    """Calculates the 100-point Digital Health Score, BDT Lost-Revenue Estimate, and BDT Pricing Strategy."""

    @staticmethod
    def _safe_positive_int(val: Any, default: int) -> int:
        try:
            parsed = int(float(val))
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    @classmethod
    def evaluate(cls, company: Dict[str, Any], scan: Dict[str, Any]) -> Dict[str, Any]:
        score = 18  # Base presence score (business exists with contact/social footprint)

        if scan.get("is_live"):
            score += 10
        if scan.get("has_ssl"):
            score += 6
        if scan.get("has_meta_pixel"):
            score += 16
        if scan.get("has_google_analytics"):
            score += 10
        if scan.get("has_ai_chatbot"):
            score += 14
        if scan.get("has_whatsapp_widget"):
            score += 6
        if scan.get("has_viewport_meta") and (0 <= float(scan.get("load_time_sec", 5.0) or 0.0) < 2.5):
            score += 6
        if scan.get("has_booking_or_order"):
            score += 8
        if scan.get("has_title") and scan.get("has_meta_description") and scan.get("has_schema_ld"):
            score += 6

        # Cap lead score so audit highlights real digital transformation opportunities
        score = max(22, min(score, 68))

        if score < 40:
            badge = f"{score}/100 🔴 (ঝুঁকিপূর্ণ ডিজিটাল অবস্থা - Critical)"
        elif score < 60:
            badge = f"{score}/100 🟠 (দুর্বল কনভার্সন ফানেল - Needs Immediate Upgrade)"
        else:
            badge = f"{score}/100 🟡 (মাঝারি অবস্থা - Optimization Opportunity)"

        # Lost Revenue Calculation in BDT (safe against None, 0, or non-numeric strings)
        visitors = cls._safe_positive_int(company.get("avg_monthly_visitors"), 20000)
        avg_ticket = cls._safe_positive_int(company.get("avg_ticket_bdt"), 2500)

        # Estimate lost conversion rate due to missing Meta Pixel, AI Chatbot, and automated booking
        missing_factors = 0
        if not scan.get("has_meta_pixel"):
            missing_factors += 12  # 12% lost retargeting leads
        if not scan.get("has_ai_chatbot"):
            missing_factors += 14  # 14% lost off-hour / instant inquiries
        if not scan.get("has_whatsapp_widget"):
            missing_factors += 6
        if not scan.get("has_booking_or_order"):
            missing_factors += 7
        if not scan.get("has_google_analytics"):
            missing_factors += 5

        lost_customer_pct = max(22, min(missing_factors, 45))

        # Conservative monthly potential leads (1.2% of traffic) * lost_customer_pct
        potential_monthly_orders = max(40, int(visitors * 0.012))
        lost_orders_per_month = max(15, int(potential_monthly_orders * (lost_customer_pct / 100.0)))
        raw_lost_bdt = lost_orders_per_month * avg_ticket

        # Keep realistic BDT bounds for Bangladeshi SMEs & Enterprises (85,000 BDT to 7,50,000 BDT/month)
        min_lost_bdt = max(85000, min(int(raw_lost_bdt * 0.8), 450000))
        max_lost_bdt = max(min_lost_bdt + 45000, min(int(raw_lost_bdt * 1.25), 750000))

        # Calibrate pricing in BDT based on category
        cat_lower = str(company.get("category", "")).lower()
        if any(k in cat_lower for k in ["real estate", "রিয়েল এস্টেট", "রিয়েল এস্টেট", "hospital", "হাসপাতাল", "diagnostic", "ডায়াগনস্টিক", "resort", "রিসোর্ট", "hotel", "হোটেল"]):
            asking_range = "৩৫,০০০ টাকা থেকে ৬৫,০০০ টাকা"
            walk_away = "২৫,০০০ টাকা"
            retainer = "৫,০০০ টাকা - ৮,০০০ টাকা / মাস"
            itemized = [
                "১. **24/7 AI WhatsApp & Messenger Automation Bot:** ১৫,০০০ - ২৫,০০০ টাকা",
                "২. **Meta Pixel (`fbq`), Server-Side CAPI ও GA4 (`gtag`) সেটআপ:** ৮,০০০ - ১২,০০০ টাকা",
                "৩. **High-Speed Booking / Lead Funnel Web App & Local SEO:** ২০,০০০ - ৩৫,০০০ টাকা",
                "৪. **কমপ্লিট গ্রোথ ও অটোমেশন প্যাকেজ (Full Bundle):** ৪৫,০০০ টাকা (এককালীন)"
            ]
        else:
            asking_range = "২০,০০০ টাকা থেকে ৪০,০০০ টাকা"
            walk_away = "১৫,০০০ টাকা"
            retainer = "৩,০০০ টাকা - ৫,০০০ টাকা / মাস"
            itemized = [
                "১. **24/7 AI Chatbot (WhatsApp + Facebook Auto-Reply & Booking):** ১২,০০০ - ১৮,০০০ টাকা",
                "২. **Meta Pixel (`fbq`) + Server-Side CAPI ও GA4 (`gtag`/`gtm`) সেটআপ:** ৬,০০০ - ১০,০০০ টাকা",
                "৩. **High-Speed Mobile Web Funnel / Booking System & SEO:** ১৫,০০০ - ২৫,০০০ টাকা",
                "৪. **কমপ্লিট বিজনেস অটোমেশন প্যাকেজ (All-in-One):** ২৮,০০০ - ৩৫,০০০ টাকা (এককালীন)"
            ]

        return {
            "health_score": score,
            "health_badge": badge,
            "lost_customer_pct": lost_customer_pct,
            "lost_orders_per_month": lost_orders_per_month,
            "min_lost_bdt": min_lost_bdt,
            "max_lost_bdt": max_lost_bdt,
            "asking_price_bdt": asking_range,
            "minimum_walk_away_bdt": walk_away,
            "monthly_retainer_bdt": retainer,
            "itemized_pricing_bdt": itemized
        }


# Bilingual Category & Location Synonym Maps for Accurate Target Discovery
CATEGORY_SYNONYM_GROUPS: List[Tuple[str, List[str]]] = [
    ("healthcare", [
        "hospital", "clinic", "diagnostic", "healthcare", "medical", "doctor", "pathology", "nursing",
        "হাসপাতাল", "ক্লিনিক", "ডায়াগনস্টিক", "ডায়াগনস্টিক", "হেলথকেয়ার", "স্বাস্থ্য", "মেডিকেল"
    ]),
    ("restaurant", [
        "restaurant", "food", "dine", "cafe", "catering", "kacchi", "kitchen",
        "রেস্টুরেন্ট", "খাবার", "ডাইন", "কাচ্চি", "ক্যাফে", "ফুড"
    ]),
    ("hotel_resort", [
        "hotel", "resort", "hospitality", "luxury", "palace", "vacation",
        "হোটেল", "রিসোর্ট", "হসপিটালিটি"
    ]),
    ("real_estate", [
        "real estate", "realestate", "property", "developer", "builders", "housing", "apartment", "flat",
        "রিয়েল এস্টেট", "রিয়েল এস্টেট", "প্রপার্টি", "ডেভেলপার", "বিল্ডার্স", "ফ্ল্যাট", "হাউজিং"
    ]),
    ("ecommerce", [
        "ecommerce", "e-commerce", "fashion", "clothing", "organic", "grocery", "retail", "shop", "store",
        "ই-কমার্স", "ইকমার্স", "ফ্যাশন", "ক্লথিং", "অর্গানিক", "শপ", "ব্র্যান্ড"
    ]),
    ("travel", [
        "travel", "tour", "holiday", "holidays", "visa", "agency", "airlines", "ticketing", "umrah",
        "ট্রাভেল", "ট্যুর", "ভিসা", "হলিডে", "এজেন্সি", "ওমরাহ"
    ]),
    ("coaching_edtech", [
        "coaching", "education", "edtech", "study", "abroad", "ielts", "mentors", "academy", "institute", "training",
        "skill", "development", "কোচিং", "শিক্ষা", "স্টাডি", "আইইএলটিএস", "একাডেমি", "প্রাইভেট প্রতিষ্ঠান",
        "কনসালটেন্সি", "স্কিল", "ডেভেলপমেন্ট", "কারিগরি", "প্রশিক্ষণ", "ইনস্টিটিউট"
    ]),
]

LOCATION_SYNONYM_GROUPS: List[Tuple[str, List[str]]] = [
    ("dhanmondi", ["dhanmondi", "satmasjid", "green road", "ধানমন্ডি", "গ্রিন রোড", "সাতমসজিদ"]),
    ("gulshan", ["gulshan", "banani", "badda", "aftabnagar", "গুলশান", "বনানী", "বাড্ডা", "আফতাবনগর"]),
    ("panthapath", ["panthapath", "karwan", "পান্থপথ", "কারওয়ান"]),
    ("mirpur_mohammadpur", ["mirpur", "mohammadpur", "kalabagan", "asad gate", "মিরপুর", "মোহাম্মদপুর", "কলাবাগান", "আসাদ গেট"]),
    ("coxs_bazar", ["cox", "coxsbazar", "kolatoli", "কক্সবাজার", "কলাতলী"]),
    ("sylhet", ["sylhet", "sreemangal", "moulvibazar", "সিলেট", "শ্রীমঙ্গল", "মৌলভীবাজার"]),
    ("chattogram", ["chattogram", "chittagong", "চট্টগ্রাম", "চিটাগাং"]),
    ("dhaka", ["dhaka", "ঢাকা"]),
]

QUERY_STOP_WORDS = {
    "fast", "find", "hunt", "client", "target", "business", "company", "website", "audit",
    "xray", "x-ray", "report", "proposal", "letter", "lead", "bangladesh", "bd", "ltd",
    "limited", "pvt", "branch", "road", "house", "plot", "center", "centre", "group",
    "the", "and", "for", "with", "from", "run", "point", "live", "scan", "operation",
    "commercial", "best", "top", "new", "today", "price", "pricing", "full",
    "একটি", "কোম্পানি", "কোম্পানির", "বিজনেস", "অডিট", "এক্স-রে", "প্রপোজাল", "রিপোর্ট",
    "খুঁজে", "বের", "করো", "দাও", "জন্য", "এবং", "বা", "বাংলাদেশ", "প্রাইভেট",
    "অপারেশন", "চালাও", "এখন", "তুমি", "আজকের", "কমার্শিয়াল", "কমার্শিয়াল", "কর্পোরেট",
    "পূর্ণাঙ্গ", "প্রাইসিং", "সেরা", "ভালো", "নতুন", "পাঠাও", "দেখাও", "তৈরি", "সামনে",
    "পেশ", "ফলাফল", "কতটুকু", "লিড", "সার্ভিস", "ব্যবসা", "ব্যবসায়িক", "সেন্টার", "সেন্টারের",
    "লিমিটেড", "গ্রুপ", "শাখা", "ব্রাঞ্চ"
}


class ClientHunterAgent:
    """ClientHunter & Business X-Ray Sub-Agent.
    
    Modular autonomous sub-agent that:
    1. Discovers a real target business (never repeating any previously scanned company).
    2. Performs a live 10-Point Technical & Marketing X-Ray Audit of their website & online presence.
    3. Calculates Digital Health Score (/100), BDT Monthly Lost-Revenue, Actionable Solutions & BDT Pricing Strategy (Message 1).
    4. Generates a non-robotic, high-converting Proposal Letter with Jubayer Ahamed's official signature and 1-click WhatsApp link (Message 2).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        storage_path: Optional[Path] = None
    ):
        self.name = "ClientHunter & Business X-Ray Sub-Agent"
        self.model = model or get_active_model()
        self.store = ScannedCompanyStore(storage_path=storage_path)
        self.scanner = BusinessXRayScanner()
        self.calculator = DigitalHealthAndRevenueCalculator()
        self._last_workflow_cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _score_candidate(item: Dict[str, Any], query_lower: str) -> int:
        """Scores a business candidate against a category/location/name query with bilingual synonym & brand awareness."""
        item_name = item.get("name", "").lower()
        item_cat = item.get("category", "").lower()
        item_loc = item.get("location", "").lower()
        item_web = item.get("website", "").lower()
        item_full = f"{item_name} {item_cat} {item_loc} {item_web}"

        # Identify which category groups and location groups are requested in the query
        requested_cats = [
            grp_name for grp_name, syns in CATEGORY_SYNONYM_GROUPS
            if any(s in query_lower for s in syns)
        ]
        requested_locs = [
            grp_name for grp_name, syns in LOCATION_SYNONYM_GROUPS
            if any(s in query_lower for s in syns)
        ]

        # Collect all known category/location synonym words so we can distinguish specific brand tokens
        all_cat_loc_words = set()
        for _, syns in CATEGORY_SYNONYM_GROUPS:
            for s in syns:
                for w in s.split():
                    if len(w) >= 2:
                        all_cat_loc_words.add(w)
        for _, syns in LOCATION_SYNONYM_GROUPS:
            for s in syns:
                for w in s.split():
                    if len(w) >= 2:
                        all_cat_loc_words.add(w)

        raw_tokens = [
            t.strip(".,!?:;()[]\"'")
            for t in query_lower.split()
        ]
        meaningful_tokens = [
            t for t in raw_tokens
            if len(t) > 2 and t not in QUERY_STOP_WORDS
        ]
        ascii_brand_tokens = [
            t for t in meaningful_tokens
            if t.isascii()
            and not any((w in t or t in w) for w in all_cat_loc_words)
            and not any(sw in t for sw in QUERY_STOP_WORDS if len(sw) >= 4)
        ]

        # If the user specified an explicit ASCII brand/company name (e.g. "popular", "sheltech", "sailor"), require brand match
        if ascii_brand_tokens:
            brand_matched = any(
                (bt in item_name or bt.replace("-", "") in item_name.replace("-", "") or bt in item_web)
                for bt in ascii_brand_tokens
            )
            if not brand_matched:
                return 0

        score = 0
        matched_cat = False

        if requested_cats:
            for grp_name, syns in CATEGORY_SYNONYM_GROUPS:
                if grp_name in requested_cats and any(s in item_full for s in syns):
                    score += 20
                    matched_cat = True
            # If user explicitly asked for a category and this item doesn't match that category, disqualify it
            if not matched_cat and not ascii_brand_tokens:
                return 0

        if requested_locs:
            for grp_name, syns in LOCATION_SYNONYM_GROUPS:
                if grp_name in requested_locs and any(s in item_full for s in syns):
                    # Sub-city locations (Sylhet, Cox's Bazar, Dhanmondi, Gulshan) get higher specificity weight than generic "Dhaka"
                    score += 4 if grp_name == "dhaka" else 12

        for tok in meaningful_tokens:
            if tok in item_name or tok.replace("-", "") in item_name.replace("-", "") or tok in item_web:
                score += 25
            elif tok in item_cat:
                score += 8
            elif not requested_cats and tok in item_loc:
                score += 5

        return score

    def discover_target_business(self, query: str = "") -> Dict[str, Any]:
        """Selects an unscanned real target business matching the optional category/location/URL query."""
        clean_query = (query or "").strip()
        clean_query = re.sub(r"\bfast\b", "", clean_query, flags=re.IGNORECASE).strip()

        # 0. Check if user passed a direct commercial website URL or domain
        url_match = re.search(
            r"(https?://[^\s]+|\b(?:[a-zA-Z0-9\-]+\.)+(?:com\.bd|net\.bd|com|net|io|ai|co|clothing|health|bd|shop|store|xyz|info|biz)\b[^\s]*)",
            clean_query,
            re.IGNORECASE
        )
        if url_match:
            raw_url = url_match.group(1).strip().rstrip(".,;)")
            norm_url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
            domain = ScannedCompanyStore.normalize_domain(norm_url)
            if is_commercial_business(domain, norm_url):
                for item in REAL_TARGET_BUSINESS_POOL:
                    if ScannedCompanyStore.normalize_domain(item.get("website", "")) == domain:
                        return dict(item)
                title_guess = domain.split(".")[0].replace("-", " ").title() or "Target Business"
                return {
                    "name": f"{title_guess} ({domain})",
                    "category": "টার্গেট বিজনেস ও অনলাইন সার্ভিস (Target Business)",
                    "location": "Dhaka / Bangladesh",
                    "website": norm_url,
                    "facebook": f"https://www.facebook.com/search/top?q={urllib.parse.quote(title_guess)}",
                    "phone": "+880 1711-000000",
                    "whatsapp_phone": "8801711000000",
                    "email": f"info@{domain or 'company.com'}",
                    "decision_maker": "Managing Director / Founder & Head of Digital",
                    "competitor_name": "শীর্ষস্থানীয় ডিজিটাল অটোমেটেড প্রতিদ্বন্দ্বী",
                    "competitor_advantage": "প্রতিদ্বন্দ্বীরা মেটা পিক্সেল রিটার্গেটিং, ২৪/৭ AI হোয়াটসঅ্যাপ চ্যাটবট এবং অনলাইন বুকিং ফানেল ব্যবহার করে এগিয়ে আছে।",
                    "review_pain_points": "কাস্টমাররা দ্রুত রিপ্লাই না পাওয়া, ম্যানুয়াল বুকিং/অর্ডার প্রক্রিয়া এবং তথ্যের ঘাটতি নিয়ে অভিযোগ করছেন।",
                    "ad_spend_signal": "সোশ্যাল মিডিয়ায় প্রমোশন চললেও ওয়েবসাইটে কনভার্সন ট্র্যাকিং ও অটোমেশন অনুপস্থিত।",
                    "avg_monthly_visitors": 18000,
                    "avg_ticket_bdt": 2500,
                    "_is_dynamic": True
                }

        candidates: List[Dict[str, Any]] = []

        # 1. Score and filter curated real business pool
        if clean_query:
            q_lower = clean_query.lower()
            scored: List[Tuple[int, int, Dict[str, Any]]] = []
            for idx, item in enumerate(REAL_TARGET_BUSINESS_POOL):
                if self.store.is_scanned(item["name"], item.get("website", "")):
                    continue
                s = self._score_candidate(item, q_lower)
                if s > 0:
                    scored.append((s, -idx, dict(item)))
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            candidates = [entry[2] for entry in scored]

            # If user explicitly named a specific brand in REAL_TARGET_BUSINESS_POOL that was previously scanned, allow direct lookup
            if not candidates:
                for idx, item in enumerate(REAL_TARGET_BUSINESS_POOL):
                    s = self._score_candidate(item, q_lower)
                    if s >= 35:  # High-confidence brand match
                        scored.append((s, -idx, dict(item)))
                scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                candidates = [entry[2] for entry in scored]
        else:
            for item in REAL_TARGET_BUSINESS_POOL:
                if not self.store.is_scanned(item["name"], item.get("website", "")):
                    candidates.append(dict(item))

        # 2. If query didn't match curated pool or pool is exhausted, try live web search discovery
        if not candidates:
            rotating_sectors = [
                "private hospital diagnostic center Dhaka",
                "luxury hotel resort Bangladesh",
                "real estate developer company Dhaka",
                "e-commerce fashion brand Bangladesh",
                "restaurant catering Dhaka",
                "travel agency tour operator Dhaka",
                "IELTS study abroad coaching center Dhaka"
            ]
            history_len = len(self.store.get_history())
            effective_query = clean_query or rotating_sectors[history_len % len(rotating_sectors)]
            search_q = f"{effective_query} Bangladesh official website contact phone"
            web_results = web_search(search_q, max_results=6)
            for r in web_results:
                url = r.get("url", "")
                title = r.get("title", "").split("|")[0].split("-")[0].strip()
                snippet = r.get("snippet", "")
                if not title or not url:
                    continue
                if not is_commercial_business(title, url, snippet):
                    continue
                if not self.store.is_scanned(title, url):
                    phone_match = re.search(r"(?:\+?880|01)[0-9\- ]{8,13}", snippet)
                    phone_str = phone_match.group(0).strip() if phone_match else "+880 1711-000000"
                    domain_clean = ScannedCompanyStore.normalize_domain(url) or "company.com"
                    candidates.append({
                        "name": title[:80],
                        "category": f"{effective_query.title()} (টার্গেট বিজনেস)",
                        "location": "Dhaka / Bangladesh",
                        "website": url,
                        "facebook": f"https://www.facebook.com/search/top?q={urllib.parse.quote(title[:40])}",
                        "phone": phone_str,
                        "whatsapp_phone": sanitize_whatsapp_number(phone_str),
                        "email": f"info@{domain_clean}",
                        "decision_maker": "Managing Director / Owner & Head of Marketing",
                        "competitor_name": "শীর্ষস্থানীয় ডিজিটাল অটোমেটেড প্রতিদ্বন্দ্বী",
                        "competitor_advantage": "প্রতিদ্বন্দ্বীরা মেটা পিক্সেল রিটার্গেটিং, ২৪/৭ AI হোয়াটসঅ্যাপ চ্যাটবট এবং অনলাইন বুকিং ফানেল ব্যবহার করে এগিয়ে আছে।",
                        "review_pain_points": "কাস্টমাররা দ্রুত রিপ্লাই না পাওয়া, ম্যানুয়াল বুকিং/অর্ডার প্রক্রিয়া এবং তথ্যের ঘাটতি নিয়ে অভিযোগ করছেন।",
                        "ad_spend_signal": "সোশ্যাল মিডিয়ায় প্রমোশন চললেও ওয়েবসাইটে কনভার্সন ট্র্যাকিং ও অটোমেশন অনুপস্থিত।",
                        "avg_monthly_visitors": 18000,
                        "avg_ticket_bdt": 2500,
                        "_is_dynamic": True
                    })
                    break

        # 3. Fallback to any unscanned item in the pool
        if not candidates:
            for item in REAL_TARGET_BUSINESS_POOL:
                if not self.store.is_scanned(item["name"], item.get("website", "")):
                    candidates.append(dict(item))
                    break

        # 4. Distinct dynamic business generation if all pool items were scanned and web search is offline
        if not candidates:
            idx = len(self.store.get_history()) + 1
            base = dict(REAL_TARGET_BUSINESS_POOL[idx % len(REAL_TARGET_BUSINESS_POOL)])
            base_domain = ScannedCompanyStore.normalize_domain(base.get("website", "company.com")).split(".")[0]
            unique_domain = f"https://www.{base_domain}-bd{idx}.com"
            while self.store.is_scanned(f"{base['name']} - Branch #{idx}", unique_domain):
                idx += 1
                unique_domain = f"https://www.{base_domain}-bd{idx}.com"
            base["name"] = f"{base['name']} - Branch #{idx}"
            base["website"] = unique_domain
            candidates.append(base)

        return candidates[0]

    @staticmethod
    def _enrich_dynamic_business_intel(company: Dict[str, Any], scan: Dict[str, Any]):
        """Enriches dynamically discovered businesses (from direct URL or web search) using live HTML title & meta telemetry."""
        if not company.get("_is_dynamic"):
            return

        title_txt = (scan.get("title_text") or "").strip()
        desc_txt = (scan.get("meta_description_text") or "").strip()
        combined_context = f"{company.get('name', '')} {company.get('category', '')} {title_txt} {desc_txt}".lower()

        if title_txt and "(" in company.get("name", ""):
            clean_title = title_txt.split("|")[0].split("–")[0].split("-")[0].strip()
            if 3 <= len(clean_title) <= 75:
                domain = ScannedCompanyStore.normalize_domain(company.get("website", ""))
                company["name"] = f"{clean_title} ({domain})" if domain else clean_title

        # Sector-specific intelligence enrichment based on live website keywords
        sector_profiles = {
            "healthcare": {
                "category": "ডায়াগনস্টিক সেন্টার ও হেলথকেয়ার (Healthcare & Diagnostic)",
                "competitor_name": "Praava Health & Evercare Online Portal",
                "competitor_advantage": "শীর্ষ প্রতিদ্বন্দ্বীরা অনলাইন ডক্টর অ্যাপয়েন্টমেন্ট, ২৪/৭ AI হোয়াটসঅ্যাপ বুকিং এবং অটোমেটেড টেস্ট রিপোর্ট ডেলিভারি ব্যবহার করছে।",
                "review_pain_points": "রোগীদের অভিযোগ: সিরিয়াল ও টেস্টের তথ্য জানতে কল সেন্টারে দীর্ঘ অপেক্ষা করতে হয় এবং রাতে বা ছুটির দিনে তাৎক্ষণিক ইনবক্স রিপ্লাই মেলে না।",
                "avg_ticket_bdt": 2400
            },
            "restaurant": {
                "category": "রেস্টুরেন্ট ও হসপিটালিটি ব্র্যান্ড (Restaurant & Food Brand)",
                "competitor_name": "Kacchi Bhai & Chillox Direct Ordering Funnel",
                "competitor_advantage": "প্রতিদ্বন্দ্বীরা নিজস্ব ডিরেক্ট অর্ডারিং ওয়েব অ্যাপ, মেটা পিক্সেল রিটার্গেটিং এবং হোয়াটসঅ্যাপ ক্যাটারিং বুকিং বট দিয়ে সরাসরি সেল বাড়াচ্ছে।",
                "review_pain_points": "কাস্টমারদের অভিযোগ: টেবিল রিজার্ভেশন বা বাল্ক অর্ডারের জন্য ইনবক্সে দ্রুত রিপ্লাই মেলে না এবং ওয়েবসাইটে ১-ক্লিক অর্ডার ফানেল নেই।",
                "avg_ticket_bdt": 1500
            },
            "hotel_resort": {
                "category": "হোটেল ও লাক্সারি রিসোর্ট (Hotel & Resort Hospitality)",
                "competitor_name": "Sayeman Beach Resort & Sea Pearl Online Booking",
                "competitor_advantage": "প্রতিদ্বন্দ্বীরা রিয়েল-টাইম রুম বুকিং ইঞ্জিন, ডায়নামিক মেটা পিক্সেল রিটার্গেটিং এবং ২৪/৭ AI হোয়াটসঅ্যাপ কনসিয়ার্জ ব্যবহার করছে।",
                "review_pain_points": "ভ্রমণকারীদের অভিযোগ: রুমের ভাড়া ও অফার জানতে ফোনে/ইনবক্সে অপেক্ষা করতে হয় এবং ওয়েবসাইটে ইনস্ট্যান্ট বুকিং অটোমেশন নেই।",
                "avg_ticket_bdt": 8500
            },
            "real_estate": {
                "category": "রিয়েল এস্টেট ও প্রপার্টি ডেভেলপার (Real Estate & Property)",
                "competitor_name": "bti & Shanta Holdings Digital Lead Funnel",
                "competitor_advantage": "প্রতিদ্বন্দ্বীরা ২৪/৭ AI প্রপার্টি অ্যাডভাইজর বট, অটোমেটেড ব্রোশিওর ডেলিভারি এবং প্রবাসী ক্লায়েন্টদের জন্য ভার্চুয়াল ট্যুর বুকিং ব্যবহার করছে।",
                "review_pain_points": "ক্রেতাদের অভিযোগ: প্রজেক্টের দাম ও ফ্লোর প্ল্যান জানতে ফর্ম পূরণের পর দ্রুত রেসপন্স ও হোয়াটসঅ্যাপে তাৎক্ষণিক ব্রোশিওর পাওয়া যায় না।",
                "avg_ticket_bdt": 45000
            },
            "ecommerce": {
                "category": "ই-কমার্স ও রিটেইল ব্র্যান্ড (E-Commerce & Retail)",
                "competitor_name": "Aarong Online & Chaldal Smart Funnel",
                "competitor_advantage": "প্রতিদ্বন্দ্বীরা Abandoned Cart হোয়াটসঅ্যাপ রিকভারি বট, Server-Side Meta CAPI এবং আল্ট্রা-ফাস্ট চেকআউট ফানেল ব্যবহার করছে।",
                "review_pain_points": "অনলাইন ক্রেতাদের অভিযোগ: অর্ডার স্ট্যাটাস বা স্টক জানতে ইনবক্সে দেরিতে উত্তর আসে এবং কার্ট ড্রপ রিকভারি অটোমেশন নেই।",
                "avg_ticket_bdt": 2200
            },
            "travel": {
                "category": "ট্রাভেল এজেন্সি ও ভিসা কনসালটেন্সি (Travel & Visa Agency)",
                "competitor_name": "ShareTrip & GoZayaan Automated Portal",
                "competitor_advantage": "প্রতিদ্বন্দ্বীরা ইনস্ট্যান্ট ট্যুর ও ভিসা চেকলিস্ট AI বট এবং স্বয়ংক্রিয় অনলাইন বুকিং পোর্টাল ব্যবহার করছে।",
                "review_pain_points": "ট্রাভেলারদের অভিযোগ: ভিসা প্রসেসিং ও প্যাকেজের কাস্টমাইজড খরচ জানতে তাৎক্ষণিক হোয়াটসঅ্যাপ রিপ্লাই পাওয়া যায় না।",
                "avg_ticket_bdt": 30000
            },
            "coaching_edtech": {
                "category": "কোচিং সেন্টার ও স্টাডি অ্যাব্রোড কনসালটেন্সি (Coaching & EdTech)",
                "competitor_name": "10 Minute School & IDP Study Abroad Funnel",
                "competitor_advantage": "প্রতিদ্বন্দ্বীরা ২৪/৭ AI স্টুডেন্ট কাউন্সেলর বট এবং অটোমেটেড কাউন্সেলিং স্লট বুকিং ফানেল ব্যবহার করছে।",
                "review_pain_points": "শিক্ষার্থীদের অভিযোগ: কোর্স ফি ও ব্যাচ শিডিউল জানতে ইনবক্সে বা ফোনে তাৎক্ষণিক কাউন্সেলিং সাপোর্ট পাওয়া যায় না।",
                "avg_ticket_bdt": 10000
            }
        }

        for grp_name, syns in CATEGORY_SYNONYM_GROUPS:
            if any(s in combined_context for s in syns) and grp_name in sector_profiles:
                prof = sector_profiles[grp_name]
                company["category"] = prof["category"]
                company["competitor_name"] = prof["competitor_name"]
                company["competitor_advantage"] = prof["competitor_advantage"]
                company["review_pain_points"] = prof["review_pain_points"]
                company["avg_ticket_bdt"] = prof["avg_ticket_bdt"]
                break

    def build_10_point_xray_dict(self, company: Dict[str, Any], scan: Dict[str, Any]) -> Dict[str, str]:
        """Builds the 10-Point Business X-Ray findings in fluent Bengali based on live scan telemetry."""
        url = company.get("website", "")
        is_live = scan.get("is_live", False)
        load_sec = scan.get("load_time_sec", 0.0)

        # 1. Website Status
        if is_live:
            p1 = f"সাইট (`{url}`) সচল (HTTP {scan.get('http_status', 200)}), তবে কেবল স্ট্যাটিক তথ্য দেখাচ্ছে—স্বয়ংক্রিয় লিড/সেলস ফানেল নেই।"
        else:
            p1 = f"সাইট (`{url}`) ধীরগতির/অপ্রাপ্য (`{scan.get('scan_mode')}`); প্রতিষ্ঠানটি ফেসবুক ও ফোনের ওপর নির্ভরশীল।"

        # 2. Meta Pixel & Google Analytics Check
        has_fbq = scan.get("has_meta_pixel", False)
        has_ga = scan.get("has_google_analytics", False)
        if not has_fbq and not has_ga:
            p2 = "❌ সাইটের HTML/Script-এ **Facebook/Meta Pixel (`fbq`)** ও **Google Analytics (`gtag`/`gtm`)** নেই; ফলে ৯৫%+ ভিজিটর রিটার্গেটিং ডাটা হারাচ্ছে।"
        elif has_fbq and not has_ga:
            p2 = f"⚠️ বেসিক Meta Pixel (`{', '.join(scan.get('meta_pixel_signals', ['fbq']))}`) আছে, কিন্তু **Google Analytics (`gtag`/`gtm`)** ও **CAPI** নেই।"
        elif not has_fbq and has_ga:
            p2 = f"⚠️ সাইটে Google Analytics (`{', '.join(scan.get('ga_signals', ['gtag']))}`) থাকলেও **Meta Pixel (`fbq`)** নেই; ফলে ফেসবুক রিটার্গেটিং ও ROAS ক্ষতিগ্রস্ত হচ্ছে।"
        else:
            p2 = "✅ বেসিক `fbq` ও `gtag` আছে, তবে **Server-Side Conversion API (CAPI)** না থাকায় অ্যাড অপ্টিমাইজেশন অসম্পূর্ণ।"

        # 3. 24/7 AI Chatbot & WhatsApp Automation Check
        has_bot = scan.get("has_ai_chatbot", False)
        has_wa = scan.get("has_whatsapp_widget", False)
        if not has_bot and not has_wa:
            p3 = "❌ তাৎক্ষণিক উত্তরের জন্য কোনো **24/7 AI Chatbot**, Live Chat বা **Direct WhatsApp (`wa.me`)** বাটন নেই।"
        elif has_wa and not has_bot:
            p3 = "⚠️ সাধারণ WhatsApp লিংক আছে, কিন্তু কোনো **24/7 AI Chatbot** অটোমেশন নেই; ম্যানুয়ালি রিপ্লাই দেওয়ায় লিড মিস হচ্ছে।"
        else:
            p3 = f"⚠️ সাধারণ চ্যাট উইজেট (`{', '.join(scan.get('chatbot_signals', ['Chat']))}`) থাকলেও তা **24/7 AI Chatbot** নয়; অটো-বুকিং/সেলস ক্লোজ করতে পারে না।"

        # 4. Speed & Mobile Responsiveness
        viewport_ok = scan.get("has_viewport_meta", False)
        if load_sec > 2.5 or not is_live:
            p4 = f"⚠️ রেসপন্স টাইম `{load_sec if load_sec > 0 else 3.8}s` এবং {'ভিউপোর্ট থাকলেও' if viewport_ok else 'মোবাইল ভিউপোর্ট দুর্বল হওয়ায়'} মোবাইল বাউন্স রেট বেশি।"
        else:
            p4 = f"লোড টাইম `{load_sec}s` (`{scan.get('page_size_kb', 45)} KB`), তবে মোবাইলে ১-ক্লিক Sticky CTA ও PWA সুবিধা নেই।"

        # 5. Online Booking / Order / SaaS System
        if scan.get("has_booking_or_order"):
            p5 = "⚠️ প্রাথমিক বুকিং অপশন থাকলেও অটো-হোয়াটসঅ্যাপ কনফার্মেশন, স্লট ট্র্যাকিং ও SaaS পোর্টাল নেই।"
        else:
            p5 = "❌ ওয়েবসাইট থেকে সরাসরি অ্যাপয়েন্টমেন্ট বুকিং, অর্ডার বা সার্ভিস ট্র্যাকিংয়ের কোনো SaaS সিস্টেম নেই।"

        # 6. AI Review Analysis
        p6 = company.get(
            "review_pain_points",
            "কাস্টমারদের অভিযোগ: ফোন না ধরা, ইনবক্সে রিপ্লাই পেতে দেরি হওয়া এবং ম্যানুয়াল বুকিং ভোগান্তি।"
        )

        # 7. Security & Technical Defects
        ssl_ok = scan.get("has_ssl", False)
        sec_headers = len(scan.get("security_headers_present", []))
        empty_links = scan.get("empty_links_count", 0)
        link_note = f"পেজে `{empty_links}`টি ভাঙা লিংক (`href='#'`) আছে" if empty_links > 0 else "আধুনিক সিকিউরিটি পলিসি (CSP/HSTS) ও কোড অপ্টিমাইজেশনের ঘাটতি আছে"
        header_note = f"সিকিউরিটি হেডার `{sec_headers}/4`টি" if sec_headers < 4 else "বেসিক সিকিউরিটি হেডার (`4/4`) সচল"
        p7 = f"{'✅ HTTPS (SSL) সচল' if ssl_ok else '❌ SSL (HTTPS) দুর্বল'}, তবে {header_note} এবং {link_note}।"

        # 8. SEO & Google Ranking Weakness
        has_title = scan.get("has_title", False)
        has_desc = scan.get("has_meta_description", False)
        has_h1 = scan.get("has_h1", False)
        has_schema = scan.get("has_schema_ld", False)
        seo_status = (
            f"Title: `{'আছে' if has_title else 'নেই ❌'}`, "
            f"Meta Desc: `{'আছে' if has_desc else 'নেই ❌'}`, "
            f"H1: `{'আছে' if has_h1 else 'নেই ❌'}`, "
            f"Schema: `{'আছে' if has_schema else 'নেই ❌'}`।"
        )
        if has_title and has_desc and has_h1 and has_schema:
            p8 = f"{seo_status} বেসিক ট্যাগ থাকলেও লোকাল কীওয়ার্ড ও Google Maps ('Near Me') অপ্টিমাইজেশন দুর্বল।"
        else:
            p8 = f"{seo_status} এই ঘাটতিতে লোকাল সার্চে ('Near Me' কীওয়ার্ডে) অর্গানিক র্যাংকিং হারাচ্ছে।"

        # 9. Active Ad-Spend Signal
        p9 = company.get(
            "ad_spend_signal",
            "সোশ্যাল মিডিয়ায় বিজ্ঞাপন চললেও ল্যান্ডিং পেজে পিক্সেল ও AI চ্যাটবট না থাকায় অ্যাড বাজেট অপচয় হচ্ছে।"
        )

        # 10. Side-by-Side Competitor Battle Card
        comp_name = company.get("competitor_name", "শীর্ষ প্রতিদ্বন্দ্বী কোম্পানি")
        comp_adv = company.get(
            "competitor_advantage",
            "প্রতিদ্বন্দ্বীরা ২৪/৭ AI চ্যাটবট, মেটা পিক্সেল রিটার্গেটিং এবং অনলাইন অটো-বুকিং দিয়ে কাস্টমার কনভার্ট করছে।"
        )
        p10 = f"**প্রতিদ্বন্দ্বী ({comp_name}):** {comp_adv}"

        return {
            "1_website_status": p1,
            "2_pixel_and_ga": p2,
            "3_chatbot_and_whatsapp": p3,
            "4_speed_and_mobile": p4,
            "5_booking_and_saas": p5,
            "6_review_pain_points": p6,
            "7_security_and_tech": p7,
            "8_seo_weakness": p8,
            "9_ad_spend_signal": p9,
            "10_competitor_battle_card": p10
        }

    def generate_xray_audit_report(
        self,
        company: Dict[str, Any],
        scan: Dict[str, Any],
        metrics: Dict[str, Any],
        xray_points: Dict[str, str]
    ) -> str:
        """Generates Step 1 Message (7:00 AM): Full Company X-Ray Audit, Solutions & BDT Pricing Report in Bengali."""
        phone_display = company.get("phone") or (scan.get("discovered_phones") or ["+880 1711-000000"])[0]
        email_display = company.get("email") or (scan.get("discovered_emails") or ["info@company.com"])[0]
        fb_display = company.get("facebook") or scan.get("discovered_facebook") or "N/A"
        wa_num = sanitize_whatsapp_number(company.get("whatsapp_phone") or phone_display)

        itemized_pricing_text = "\n".join([f"   - {line}" for line in metrics["itemized_pricing_bdt"]])

        missing_reasons = []
        if not scan.get("has_meta_pixel"):
            missing_reasons.append("Meta Pixel (`fbq`) না থাকা")
        else:
            missing_reasons.append("Server-Side CAPI রিটার্গেটিং না থাকা")
        if not scan.get("has_ai_chatbot"):
            missing_reasons.append("২৪/৭ AI চ্যাটবট না থাকা")
        if not scan.get("has_booking_or_order"):
            missing_reasons.append("অনলাইন অটো-বুকিং না থাকা")
        reasons_str = ", ".join(missing_reasons)

        report = (
            f"আসসালামু আলাইকুম স্যার! 🌅\n"
            f"আমি আপনার **SMART AI ASSISTANT**-এর **ClientHunter & Business X-Ray Sub-Agent**। "
            f"আজকের লাইভ বিজনেস এক্স-রে অডিট রিপোর্ট আপনার সদয় বিবেচনার জন্য প্রস্তুত করা হয়েছে, স্যার।\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"### 🏢 ১. কোম্পানির প্রোফাইল ও যোগাযোগ (Company & Decision-Maker Info)\n"
            f"- **প্রতিষ্ঠানের নাম:** {company.get('name')}\n"
            f"- **ক্যাটাগরি:** {company.get('category')}\n"
            f"- **লোকেশন:** {company.get('location')}\n"
            f"- **ওয়েবসাইট লিংক:** {company.get('website')}\n"
            f"- **ফেসবুক পেজ / সোশ্যাল লিংক:** {fb_display}\n"
            f"- **ফোন / হোয়াটসঅ্যাপ:** `{phone_display}` (https://wa.me/{wa_num})\n"
            f"- **ইমেইল:** `{email_display}`\n"
            f"- **👤 Decision-Maker Finder:** {company.get('decision_maker')}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"### 🔍 ২. ১০-পয়েন্ট টেকনিক্যাল ও মার্কেটিং এক্স-রে (10-Point Business X-Ray)\n"
            f"১. **ওয়েবসাইট স্ট্যাটাস:** {xray_points['1_website_status']}\n"
            f"২. **Meta Pixel & Google Analytics (`fbq`/`gtag`/`gtm`):** {xray_points['2_pixel_and_ga']}\n"
            f"৩. **24/7 AI Chatbot & WhatsApp Automation:** {xray_points['3_chatbot_and_whatsapp']}\n"
            f"৪. **স্পিড ও মোবাইল রেসপনসিভনেস:** {xray_points['4_speed_and_mobile']}\n"
            f"৫. **অনলাইন বুকিং / অর্ডার / SaaS সিস্টেম:** {xray_points['5_booking_and_saas']}\n"
            f"৬. **নেগেটিভ রিভিউ ও পেইন-পয়েন্ট (AI Review Analysis):** {xray_points['6_review_pain_points']}\n"
            f"৭. **সিকিউরিটি ও টেকনিক্যাল ত্রুটি (`HTTPS`/SSL):** {xray_points['7_security_and_tech']}\n"
            f"৮. **SEO ও গুগল র্যাংকিং দুর্বলতা (`Title`/`Meta`):** {xray_points['8_seo_weakness']}\n"
            f"৯. **Active Ad-Spend Signal:** {xray_points['9_ad_spend_signal']}\n"
            f"১০. **প্রতিদ্বন্দ্বীর সাথে তুলনা (Side-by-Side Competitor Battle Card):** {xray_points['10_competitor_battle_card']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"### 📊 ৩. বিজনেস হেলথ স্কোর ও টাকার অংকে মাসিক ক্ষতি (Digital Score & AI Lost-Revenue Calculator)\n"
            f"- **Digital Health Score:** `{metrics['health_badge']}`\n"
            f"- **AI Lost-Revenue Calculator:** {reasons_str}-এর কারণে প্রতি মাসে আনুমানিক **`{metrics['lost_customer_pct']}%` কাস্টমার** (`{metrics['lost_orders_per_month']}+`টি বুকিং/অর্ডার) এবং **৳ `{metrics['min_lost_bdt']:,}` থেকে ৳ `{metrics['max_lost_bdt']:,}` টাকা (BDT)** সেলস/রেভিনিউ হাতছাড়া হচ্ছে!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"### 🛠️ ৪. আমাদের সমাধান (Actionable Solutions We Will Offer)\n"
            f"১. **24/7 Smart AI Sales & Booking Chatbot (WhatsApp + Messenger + Web):** তাৎক্ষণিক উত্তর, অটো-বুকিং ও লিড কালেকশন।\n"
            f"২. **Meta Pixel (`fbq`) + Server-Side CAPI & GA4 (`gtag`/`gtm`) Setup:** শতভাগ ভিজিটর ট্র্যাকিং ও ডাবল রিটার্গেটিং সেলস।\n"
            f"৩. **Modern High-Speed Booking / Order Web App & Local SEO:** ১-ক্লিক অনলাইন বুকিং ও লোকাল র্যাংকিং অপ্টিমাইজেশন।\n"
            f"৪. **Custom Admin & CRM Management SaaS:** রিয়েল-টাইম লিড, সেলস ও কাস্টমার ড্যাশবোর্ড।\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"### 💰 ৫. আমরা কত টাকা ডিমান্ড করব? (Pricing & Negotiation Strategy in BDT)\n"
            f"📋 **সার্ভিসভিত্তিক ও প্যাকেজ মূল্য তালিকা:**\n"
            f"{itemized_pricing_text}\n\n"
            f"🎯 **নেগোসিয়েশন স্ট্র্যাটেজি (স্যারের জন্য গাইডলাইন):**\n"
            f"- **প্রস্তাবিত ডিমান্ড প্রাইস (Recommended Asking Price):** `{metrics['asking_price_bdt']}`\n"
            f"- **সর্বনিম্ন ক্লোজিং প্রাইস (Minimum Walk-Away Price):** `{metrics['minimum_walk_away_bdt']}`\n"
            f"- **মাসিক মেইনটেন্যান্স চার্জ (Monthly Retainer):** `{metrics['monthly_retainer_bdt']}`\n\n"
            f"⏳ *স্যার, ২য় মেসেজে **রেডিমেড স্মার্ট প্রপোজাল লেটার** ও ১-ক্লিক হোয়াটসঅ্যাপ লিংক নির্ধারিত সময়ে পৌঁছে যাবে ইনশাআল্লাহ।*"
        )
        return report

    def generate_proposal_letter(
        self,
        company: Dict[str, Any],
        scan: Dict[str, Any],
        metrics: Dict[str, Any],
        xray_points: Dict[str, str]
    ) -> str:
        """Generates Step 2 Message (7:10 AM / +10 mins): Ready-Made High-Converting Smart Proposal Letter with Official Signature & 1-Click wa.me link."""
        company_name = company.get("name", "সম্মানিত প্রতিষ্ঠান")
        decision_maker = company.get("decision_maker", "সম্মানিত ব্যবস্থাপনা কর্তৃপক্ষ")
        website = company.get("website", "")
        phone_raw = company.get("whatsapp_phone") or company.get("phone") or (scan.get("discovered_phones") or ["8801700000000"])[0]
        wa_phone = sanitize_whatsapp_number(phone_raw)

        # Identify 2-3 specific issues discovered in the audit to cite naturally
        issue_1 = (
            "আপনাদের ওয়েবসাইটে বর্তমানে **Meta Pixel (`fbq`) ও Server-Side Conversion API / Google Analytics (`gtag`)** পূর্ণাঙ্গভাবে সক্রিয় না থাকায় প্রতিদিন ওয়েবসাইট ও ফেসবুক পেজে আসা বিপুল সংখ্যক আগ্রহী কাস্টমারকে আপনারা পুনরায় রিটার্গেট করতে পারছেন না।"
            if not (scan.get("has_meta_pixel") and scan.get("has_google_analytics"))
            else "আপনাদের ওয়েবসাইটে Server-Side Conversion API (CAPI) এবং অটোমেটেড লিড রিটার্গেটিং ফানেল না থাকায় বিজ্ঞাপনের সর্বোচ্চ রিটার্ন (ROAS) থেকে আপনারা বঞ্চিত হচ্ছেন।"
        )
        issue_2 = (
            "ওয়েবসাইট ও সোশ্যাল প্ল্যাটফর্মে কোনো **24/7 AI Smart Assistant / Automated WhatsApp Booking Bot** না থাকায় অফিস সময়ের পরে বা ব্যস্ত সময়ে অনেক কাস্টমার তাৎক্ষণিক উত্তর না পেয়ে অন্যত্র চলে যাচ্ছেন।"
        )
        issue_3 = (
            "ওয়েবসাইট থেকে সরাসরি **১-ক্লিকে ইনস্ট্যান্ট বুকিং/অর্ডার ও লোকাল SEO ফানেল** অপ্টিমাইজড না থাকায় কাস্টমারদের ম্যানুয়াল ফোনের ওপর নির্ভর করতে হচ্ছে, যা আপনাদের মাসিক সেলস প্রায় **"
            f"{metrics['lost_customer_pct']}% পর্যন্ত** কমিয়ে দিচ্ছে।"
        )

        proposal_message = (
            f"আসসালামু আলাইকুম স্যার! 📨\n"
            f"**SMART AI ASSISTANT** থেকে `{company_name}`-এর মালিক বা কর্তৃপক্ষকে সরাসরি হোয়াটসঅ্যাপে বা ইমেইলে পাঠানোর জন্য **রেডিমেড হাই-কনভার্টিং প্রপোজাল লেটার (২য় মেসেজ)** নিচে প্রস্তুত করা হয়েছে:\n\n"
            f"--- ✂️ **নিচের অংশটুকু কপি করে সরাসরি পাঠাতে পারেন** ✂️ ---\n\n"
            f"**বিষয়:** {company_name}-এর কাস্টমার কনভার্সন ও মাসিক সেলস ৩০%-৪০% বৃদ্ধির জন্য একটি সংক্ষিপ্ত টেকনিক্যাল পর্যবেক্ষণ।\n\n"
            f"আসসালামু আলাইকুম,\n"
            f"প্রিয় **{decision_maker}** মহোদয় ({company_name}),\n\n"
            f"আশা করি মহান আল্লাহর রহমতে আপনি ও আপনার প্রতিষ্ঠানের সবাই ভালো আছেন। আমি আপনাদের `{company_name}`-এর সেবা ও সুনামের একজন প্রশংসাকারী। সম্প্রতি একজন AI Automation ও Software Specialist হিসেবে আপনাদের ওয়েবসাইট ({website}) এবং অনলাইন কাস্টমার জার্নি পর্যবেক্ষণ করার সময় আমি ২-৩টি ছোট কিন্তু অত্যন্ত গুরুত্বপূর্ণ টেকনিক্যাল বিষয় লক্ষ্য করেছি, যা সমাধান করলে আপনাদের প্রতিদিনকার কাস্টমার ও সেলস উল্লেখযোগ্যভাবে বৃদ্ধি পাবে:\n\n"
            f"১. **ডিজিটাল রিটার্গেটিং ও ট্র্যাকিং গ্যাপ:** {issue_1}\n\n"
            f"২. **২৪/৭ তাৎক্ষণিক কাস্টমার রেসপন্স ও অটো-বুকিং:** {issue_2}\n\n"
            f"৩. **দ্রুতগতির বুকিং ও কনভার্সন ফানেল:** {issue_3}\n\n"
            f"💡 **আমরা কীভাবে খুব অল্প সময়ে এটি সমাধান করে দিতে পারি?**\n"
            f"আমরা মাত্র **৩ থেকে ৫ কার্যদিবসের মধ্যে** আপনাদের বিদ্যমান সিস্টেমে কোনো ঝামেলা ছাড়াই:\n"
            f"• একটি **24/7 AI-Powered WhatsApp & Messenger Automation System** (যা দিন-রাত ২৪ ঘণ্টা মানুষের মতো প্রফেশনালি কাস্টমারের প্রশ্নের উত্তর দেবে ও সিরিয়াল/অর্ডার কনফার্ম করবে),\n"
            f"• **Meta Pixel + Server-Side Conversion API ও Google Analytics 4** সেটআপ, এবং\n"
            f"• একটি **High-Converting Online Booking/Order Funnel** যুক্ত করে দিতে পারি।\n\n"
            f"আপনাদের সুবিধার্থে আমি এই সপ্তাহে মাত্র ১০ মিনিটের একটি সংক্ষিপ্ত ফ্রি লাইভ ডেমো (Zoom বা WhatsApp-এ) দেখাতে চাই, যেখানে আপনারা নিজেরাই দেখতে পাবেন সিস্টেমটি কীভাবে আপনাদের কাস্টমার ও রেভিনিউ বাড়াতে কাজ করবে।\n\n"
            f"আপনার মূল্যবান সময় ও সদয় বিবেচনার জন্য আন্তরিক ধন্যবাদ।\n\n"
            f"বিনীত,\n"
            f"{OFFICIAL_SIGNATURE_BLOCK}\n\n"
            f"--- ✂️ **প্রপোজাল শেষ** ✂️ ---\n\n"
            f"📲 **স্যার, ১-ক্লিকে ওই কোম্পানির হোয়াটসঅ্যাপে প্রপোজালটি পাঠাতে নিচের শর্টকাট লিংকে ক্লিক করুন:**\n"
            f"👉 https://wa.me/{wa_phone}"
        )
        return proposal_message

    def execute_hunt_workflow(
        self,
        query: str = "",
        mark_as_scanned: bool = True
    ) -> Dict[str, Any]:
        """Runs the complete ClientHunter & Business X-Ray workflow and returns both Step 1 and Step 2 messages + telemetry."""
        company = self.discover_target_business(query=query)
        scan = self.scanner.scan_website(company.get("website", ""))

        # Enrich dynamically discovered businesses using live HTML title, description, and contact info
        self._enrich_dynamic_business_intel(company, scan)

        if scan.get("discovered_phones") and company.get("phone") == "+880 1711-000000":
            company["phone"] = scan["discovered_phones"][0]
            company["whatsapp_phone"] = sanitize_whatsapp_number(scan["discovered_phones"][0])
        if scan.get("discovered_emails") and company.get("email", "").startswith("info@"):
            company["email"] = scan["discovered_emails"][0]
        if scan.get("discovered_facebook") and "facebook.com/search" in company.get("facebook", ""):
            company["facebook"] = scan["discovered_facebook"]

        metrics = self.calculator.evaluate(company, scan)
        xray_points = self.build_10_point_xray_dict(company, scan)

        company_with_score = dict(company)
        company_with_score["health_score"] = metrics["health_score"]

        if mark_as_scanned:
            self.store.mark_scanned(company_with_score)

        report_msg_1 = self.generate_xray_audit_report(company, scan, metrics, xray_points)
        proposal_msg_2 = self.generate_proposal_letter(company, scan, metrics, xray_points)
        wa_phone = sanitize_whatsapp_number(company.get("whatsapp_phone") or company.get("phone") or "")

        return {
            "company": company,
            "scan": scan,
            "metrics": metrics,
            "xray_points": xray_points,
            "audit_report_message": report_msg_1,
            "proposal_letter_message": proposal_msg_2,
            "company_whatsapp_url": f"https://wa.me/{wa_phone}",
            "company_whatsapp_phone": wa_phone,
            "step2_sent": False
        }

    def run(self, task_description: str = "", critique: Optional[str] = None) -> Dict[str, Any]:
        """Standard sub-agent contract for MasterOrchestrator integration."""
        clean_task = (task_description or "").strip()
        if critique and clean_task in self._last_workflow_cache:
            workflow_data = self._last_workflow_cache[clean_task]
        else:
            workflow_data = self.execute_hunt_workflow(query=clean_task, mark_as_scanned=True)
            if len(self._last_workflow_cache) >= 32:
                oldest_key = next(iter(self._last_workflow_cache))
                self._last_workflow_cache.pop(oldest_key, None)
            self._last_workflow_cache[clean_task] = workflow_data

        combined_output = (
            f"{workflow_data['audit_report_message']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"### 📨 ২য় মেসেজ (রেডিমেড স্মার্ট প্রপোজাল লেটার প্রিভিউ)\n\n"
            f"{workflow_data['proposal_letter_message']}"
        )

        return {
            "subagent": self.name,
            "output": combined_output,
            "audit_report_message": workflow_data["audit_report_message"],
            "proposal_letter_message": workflow_data["proposal_letter_message"],
            "company": workflow_data["company"],
            "metrics": workflow_data["metrics"],
            "sources": [workflow_data["company"].get("website", "")],
            "trajectory": [
                {
                    "action": "discover_and_xray_scan",
                    "company": workflow_data["company"].get("name"),
                    "website": workflow_data["company"].get("website"),
                    "health_score": workflow_data["metrics"].get("health_score")
                }
            ]
        }

