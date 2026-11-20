# محطات الرفع ومعالجة الصرف | منصة إنشاءات

## الملفات
- app.py — التطبيق (الملف الرئيسي)
- style.css — التنسيقات
- requirements.txt — المكتبات
- .streamlit/config.toml — الثيم (يجب أن يكون في جذر المستودع)
- .gitignore

## تشغيل محلي
    pip install -r requirements.txt
    streamlit run app.py

## النشر على Streamlit Community Cloud
1. أنشئ مستودع GitHub جديداً لهذا المجلد وحده، وضع هذه الملفات في جذره.
2. share.streamlit.io ← Create app ← اختر المستودع والفرع main ← الملف الرئيسي app.py.
3. للمستودع الخاص: Settings ← Linked accounts ← Connect here ← Authorize streamlit.
4. بعد نشر التطبيقين ضع رابط كل منهما في OTHER_APP_URL داخل app.py الآخر.
