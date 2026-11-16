"""Offline, bilingual explanations for supported OpenHub catalog projects.

Descriptions explain typical uses, not verified installation or platform support.
Keys match upstream GitHub repository identifiers in config/openhub.tsv.
"""

DESCRIPTIONS = {
  "ollama/ollama": {
    "ar": "تشغيل نماذج الذكاء الاصطناعي على جهازك محليًا.",
    "en": "Run AI models locally on your computer."
  },
  "ggml-org/llama.cpp": {
    "ar": "تشغيل نماذج لغة مضغوطة على المعالج أو كارت الشاشة.",
    "en": "Run quantized language models on CPU or GPU."
  },
  "open-webui/open-webui": {
    "ar": "واجهة محادثة ويب لإدارة النماذج المتصلة مثل Ollama.",
    "en": "Web chat interface for connected local models."
  },
  "all-hands-ai/openhands": {
    "ar": "وكيل يساعدك في البرمجة وتعديل الملفات وتنفيذ مهام التطوير.",
    "en": "AI coding agent for editing projects and running development tasks."
  },
  "openinterpreter/open-interpreter": {
    "ar": "يساعدك في تنفيذ الكود والأوامر المحلية باستخدام الذكاء الاصطناعي.",
    "en": "AI-assisted execution of local code and commands."
  },
  "systran/faster-whisper": {
    "ar": "تحويل الكلام إلى نص بسرعة باستخدام نماذج Whisper.",
    "en": "Fast speech-to-text transcription with Whisper."
  },
  "ggml-org/whisper.cpp": {
    "ar": "التعرف على الكلام محليًا باستخدام محرك C/C++.",
    "en": "Local speech recognition with a C/C++ engine."
  },
  "snakers4/silero-vad": {
    "ar": "اكتشاف وجود الكلام والصمت داخل التسجيلات الصوتية.",
    "en": "Detect speech and silence in audio streams."
  },
  "langchain-ai/langgraph": {
    "ar": "تنظيم خطوات الوكلاء الذكيين وحالة المهام.",
    "en": "Orchestrate stateful AI-agent workflows."
  },
  "langchain-ai/langchain": {
    "ar": "ربط نماذج اللغة بالأدوات والبيانات.",
    "en": "Connect language models to tools and data."
  },
  "berriai/litellm": {
    "ar": "واجهة موحدة للتعامل مع عدة مزودي نماذج ذكاء اصطناعي.",
    "en": "Unified API gateway for multiple AI providers."
  },
  "vllm-project/vllm": {
    "ar": "خدمة نماذج اللغة بكفاءة عالية على عتاد مدعوم.",
    "en": "High-throughput model serving on supported hardware."
  },
  "ml-explore/mlx": {
    "ar": "مكتبة تعلم آلي مخصصة لأجهزة Apple Silicon، ليست لويندوز مباشرة.",
    "en": "Machine-learning library optimized for Apple Silicon."
  },
  "huggingface/transformers": {
    "ar": "تحميل وتدريب وتشغيل نماذج الذكاء الاصطناعي.",
    "en": "Load, train and run machine-learning models."
  },
  "pytorch/pytorch": {
    "ar": "إطار لبناء وتدريب نماذج التعلم العميق.",
    "en": "Framework for deep-learning research and development."
  },
  "comfy-org/comfyui": {
    "ar": "تصميم مسارات توليد الصور والوسائط باستخدام العقد.",
    "en": "Node-based AI image and media generation workflows."
  },
  "invoke-ai/invokeai": {
    "ar": "واجهة لتوليد الصور وإدارتها بنماذج الذكاء الاصطناعي.",
    "en": "Generate and manage images with AI models."
  },
  "microsoft/onnxruntime": {
    "ar": "تشغيل نماذج ONNX على أنظمة وأجهزة متنوعة.",
    "en": "Run ONNX models on different platforms."
  },
  "ohf-voice/piper1-gpl": {
    "ar": "تحويل النص إلى صوت باستخدام أصوات محلية.",
    "en": "Offline text-to-speech synthesis with local voices."
  },
  "k2-fsa/sherpa-onnx": {
    "ar": "أدوات للتعرف على الكلام ومعالجته محليًا.",
    "en": "Offline speech recognition and audio processing."
  },
  "cursortouch/windows-mcp": {
    "ar": "ربط أدوات التحكم في ويندوز بمساعد ذكاء اصطناعي.",
    "en": "Expose Windows desktop controls to AI assistants."
  },
  "browser-use/browser-use": {
    "ar": "أتمتة مهام المتصفح باستخدام الوكلاء الذكيين.",
    "en": "Browser automation for AI-driven tasks."
  },
  "microsoft/playwright": {
    "ar": "أتمتة واختبار متصفحات Chromium وFirefox وWebKit.",
    "en": "Automate and test modern web browsers."
  },
  "seleniumhq/selenium": {
    "ar": "أتمتة التفاعل والاختبارات داخل المتصفحات.",
    "en": "Automate browser interactions and testing."
  },
  "pywinauto/pywinauto": {
    "ar": "أتمتة النوافذ وعناصر واجهة برامج ويندوز.",
    "en": "Automate Windows application interfaces."
  },
  "autohotkey/autohotkey": {
    "ar": "إنشاء اختصارات وأتمتة للفأرة ولوحة المفاتيح.",
    "en": "Automate keyboard, mouse and Windows workflows."
  },
  "robotframework/robotframework": {
    "ar": "إطار للأتمتة والاختبارات باستخدام كلمات مفتاحية.",
    "en": "Keyword-driven testing and automation framework."
  },
  "aisingapore/tagui": {
    "ar": "أتمتة مهام المتصفح والعمليات المتكررة.",
    "en": "Automate web and repetitive desktop tasks."
  },
  "microsoft/powertoys": {
    "ar": "أدوات مايكروسوفت للإنتاجية وإدارة نوافذ ويندوز.",
    "en": "Microsoft productivity and window-management utilities."
  },
  "microsoft/terminal": {
    "ar": "تطبيق طرفية حديث لفتح PowerShell والأوامر.",
    "en": "Modern terminal for PowerShell and command-line tools."
  },
  "powershell/powershell": {
    "ar": "صدفة وسكربتات لإدارة النظام وتنفيذ الأوامر.",
    "en": "Shell and scripting tools for system administration."
  },
  "rocksdanister/lively": {
    "ar": "تشغيل خلفيات حية ومتحركة على ويندوز.",
    "en": "Animated and interactive Windows wallpapers."
  },
  "flow-launcher/flow.launcher": {
    "ar": "مشغل سريع للبحث عن الملفات والبرامج وفتحها.",
    "en": "Quickly search for and launch apps or files."
  },
  "srwi/everythingtoolbar": {
    "ar": "دمج بحث الملفات السريع مع شريط المهام.",
    "en": "Fast file search integrated with the taskbar."
  },
  "file-new-project/eartrumpet": {
    "ar": "التحكم المنفصل في صوت البرامج على ويندوز.",
    "en": "Per-application audio volume controls."
  },
  "valinet/explorerpatcher": {
    "ar": "تخصيص شريط المهام وبعض عناصر مستكشف ويندوز.",
    "en": "Customize Windows Explorer and taskbar features."
  },
  "open-shell/open-shell-menu": {
    "ar": "تخصيص قائمة ابدأ وشكل التنقل في ويندوز.",
    "en": "Customize the classic Windows Start menu."
  },
  "translucenttb/translucenttb": {
    "ar": "تغيير شفافية ومظهر شريط مهام ويندوز.",
    "en": "Customize Windows taskbar transparency."
  },
  "sharex/sharex": {
    "ar": "التقاط الشاشة وتسجيلها ومشاركتها.",
    "en": "Capture, record and share screenshots."
  },
  "git/git": {
    "ar": "تتبع تغييرات الملفات وإدارة تاريخ المشروع.",
    "en": "Version control for source code and project files."
  },
  "cli/cli": {
    "ar": "إدارة مستودعات GitHub وطلبات الدمج من الطرفية.",
    "en": "Manage GitHub repositories and pull requests in a terminal."
  },
  "nodejs/node": {
    "ar": "بيئة تشغيل JavaScript وأدوات تطوير الويب.",
    "en": "JavaScript runtime for apps and web tooling."
  },
  "python/cpython": {
    "ar": "لغة برمجة للأتمتة وتطوير التطبيقات.",
    "en": "General-purpose language for scripting and applications."
  },
  "rust-lang/rust": {
    "ar": "لغة لتطوير برامج سريعة وآمنة الذاكرة.",
    "en": "Programming language for performant, memory-safe software."
  },
  "tauri-apps/tauri": {
    "ar": "بناء تطبيقات سطح مكتب بواجهة ويب وخلفية Rust.",
    "en": "Desktop apps with a web UI and Rust backend."
  },
  "electron/electron": {
    "ar": "بناء تطبيقات سطح مكتب باستخدام تقنيات الويب.",
    "en": "Cross-platform desktop apps with web technologies."
  },
  "vitejs/vite": {
    "ar": "خادم تطوير وأداة بناء سريعة لتطبيقات الويب.",
    "en": "Fast web development server and build tool."
  },
  "facebook/react": {
    "ar": "مكتبة لبناء واجهات المستخدم التفاعلية.",
    "en": "Library for building interactive user interfaces."
  },
  "microsoft/typescript": {
    "ar": "إضافة أنواع ثابتة إلى JavaScript لاكتشاف الأخطاء.",
    "en": "Typed JavaScript for safer application development."
  },
  "neovim/neovim": {
    "ar": "محرر كود متقدم يعمل من الطرفية.",
    "en": "Extensible terminal-based code editor."
  },
  "notepad-plus-plus/notepad-plus-plus": {
    "ar": "محرر نصوص خفيف ومتقدم لويندوز.",
    "en": "Feature-rich lightweight Windows text editor."
  },
  "zed-industries/zed": {
    "ar": "محرر كود سريع مع أدوات تطوير وتعاون.",
    "en": "Fast collaborative code editor."
  },
  "burntsushi/ripgrep": {
    "ar": "بحث سريع داخل الملفات والمشاريع النصية.",
    "en": "Fast search across source and text files."
  },
  "sharkdp/fd": {
    "ar": "البحث بسرعة عن أسماء الملفات والمجلدات.",
    "en": "Fast file and directory name finder."
  },
  "astral-sh/uv": {
    "ar": "مدير سريع لحزم Python والبيئات الافتراضية.",
    "en": "Fast Python package and environment manager."
  },
  "astral-sh/ruff": {
    "ar": "أداة لفحص وتنسيق كود Python بسرعة.",
    "en": "Fast Python linter and formatter."
  },
  "fastapi/fastapi": {
    "ar": "إطار Python لإنشاء واجهات برمجة التطبيقات.",
    "en": "Python framework for APIs and web services."
  },
  "encode/uvicorn": {
    "ar": "خادم لتشغيل تطبيقات Python بنظام ASGI.",
    "en": "ASGI server for Python web applications."
  },
  "golang/go": {
    "ar": "لغة برمجة لبناء خدمات وأدوات موثوقة.",
    "en": "Programming language for services and tools."
  },
  "denoland/deno": {
    "ar": "بيئة لتشغيل JavaScript وTypeScript بأدوات مدمجة.",
    "en": "JavaScript and TypeScript runtime with built-in tooling."
  },
  "oven-sh/bun": {
    "ar": "بيئة تشغيل JavaScript مع أدوات للحزم والاختبار.",
    "en": "JavaScript runtime with package and test tools."
  },
  "kitware/cmake": {
    "ar": "نظام لإعداد وبناء المشاريع البرمجية.",
    "en": "Cross-platform project build configuration."
  },
  "ninja-build/ninja": {
    "ar": "أداة سريعة لتنفيذ خطوات بناء البرامج.",
    "en": "Fast executor for generated build tasks."
  },
  "amir1376/ab-download-manager": {
    "ar": "مدير تنزيلات رسومي لتنظيم وتسريع التحميلات.",
    "en": "Graphical manager for organizing and accelerating downloads."
  },
  "yt-dlp/yt-dlp": {
    "ar": "تنزيل وسائط من مواقع مدعومة وفق شروطها.",
    "en": "Download media from supported websites."
  },
  "aria2/aria2": {
    "ar": "مدير تنزيلات من الطرفية يدعم اتصالات متعددة.",
    "en": "Command-line downloader with parallel connections."
  },
  "qbittorrent/qbittorrent": {
    "ar": "عميل لتنزيل وتبادل ملفات BitTorrent.",
    "en": "BitTorrent client for downloads and sharing."
  },
  "transmission/transmission": {
    "ar": "عميل خفيف لتبادل ملفات BitTorrent.",
    "en": "Lightweight BitTorrent file-sharing client."
  },
  "agalwood/motrix": {
    "ar": "مدير تنزيلات بواجهة رسومية وروابط متعددة.",
    "en": "Graphical download manager for multiple protocols."
  },
  "videolan/vlc": {
    "ar": "مشغل فيديو وصوت يدعم صيغًا كثيرة.",
    "en": "Media player supporting many audio and video formats."
  },
  "ffmpeg/ffmpeg": {
    "ar": "تحويل وترميز ومعالجة ملفات الصوت والفيديو.",
    "en": "Convert, encode and process audio/video files."
  },
  "obsproject/obs-studio": {
    "ar": "تسجيل الشاشة والبث المباشر ومزج المصادر.",
    "en": "Screen recording, streaming and source mixing."
  },
  "audacity/audacity": {
    "ar": "تسجيل وتحرير وتنظيف الملفات الصوتية.",
    "en": "Record and edit audio files."
  },
  "handbrake/handbrake": {
    "ar": "ضغط وتحويل ملفات الفيديو بإعدادات جاهزة.",
    "en": "Convert and compress videos with presets."
  },
  "mpv-player/mpv": {
    "ar": "مشغل وسائط خفيف وقابل للتخصيص.",
    "en": "Lightweight configurable media player."
  },
  "kde/kdenlive": {
    "ar": "مونتاج فيديو متعدد المسارات والمؤثرات.",
    "en": "Multitrack video editor with effects."
  },
  "mltframework/shotcut": {
    "ar": "محرر فيديو مجاني بواجهة رسومية.",
    "en": "Free graphical video editor."
  },
  "mifi/lossless-cut": {
    "ar": "قص ملفات الصوت والفيديو بسرعة دون ترميز كامل عند الإمكان.",
    "en": "Fast lossless trimming of audio and video."
  },
  "jellyfin/jellyfin": {
    "ar": "خادم وسائط شخصي لتنظيم وبث الأفلام والموسيقى.",
    "en": "Personal server to organize and stream media."
  },
  "xbmc/xbmc": {
    "ar": "مركز وسائط لتصفح وتشغيل المحتوى المحلي.",
    "en": "Media center for browsing and playing content."
  },
  "blender/blender": {
    "ar": "تصميم ومجسمات وتحريك ورندر ثلاثي الأبعاد.",
    "en": "3D modeling, animation and rendering."
  },
  "freecad/freecad": {
    "ar": "تصميم نماذج CAD هندسية تعتمد القياسات.",
    "en": "Parametric CAD modeling for engineering."
  },
  "openscad/openscad": {
    "ar": "تصميم مجسمات ثلاثية الأبعاد بواسطة الكود.",
    "en": "Programmatic 3D model creation with code."
  },
  "prusa3d/prusaslicer": {
    "ar": "تجهيز نماذج الطباعة ثلاثية الأبعاد وتوليد G-code.",
    "en": "Slice 3D models into printable G-code."
  },
  "softfever/orcaslicer": {
    "ar": "تقطيع نماذج الطباعة وضبط إعدادات الطابعات.",
    "en": "3D printing slicer with advanced tuning."
  },
  "bambulab/bambustudio": {
    "ar": "تحضير وإدارة مهام الطباعة لطابعات Bambu Lab.",
    "en": "Prepare printing jobs for Bambu Lab printers."
  },
  "ultimaker/cura": {
    "ar": "تقطيع نماذج ثلاثية الأبعاد وتجهيز الطباعة.",
    "en": "3D printer slicing software."
  },
  "godotengine/godot": {
    "ar": "محرك ألعاب مفتوح المصدر ثنائي وثلاثي الأبعاد.",
    "en": "Open-source 2D and 3D game engine."
  },
  "kde/krita": {
    "ar": "رسم وتلوين رقمي وأعمال فنية متعددة الطبقات.",
    "en": "Digital painting and illustration."
  },
  "gnome/gimp": {
    "ar": "تحرير الصور وتنقيحها وتصميم الرسومات.",
    "en": "Raster image editing and retouching."
  },
  "localsend/localsend": {
    "ar": "نقل ملفات بين الأجهزة على الشبكة المحلية.",
    "en": "Transfer files between devices on local networks."
  },
  "syncthing/syncthing": {
    "ar": "مزامنة المجلدات والملفات بين أجهزة متعددة.",
    "en": "Synchronize files across devices."
  },
  "wireshark/wireshark": {
    "ar": "تحليل حزم الشبكة وتشخيص الاتصالات.",
    "en": "Inspect network packets for diagnostics."
  },
  "curl/curl": {
    "ar": "نقل البيانات وطلبات HTTP من سطر الأوامر.",
    "en": "Transfer data and make HTTP requests."
  },
  "rclone/rclone": {
    "ar": "مزامنة الملفات بين التخزين المحلي والسحابي.",
    "en": "Sync and transfer local or cloud files."
  },
  "caddyserver/caddy": {
    "ar": "خادم ويب ووكيل عكسي مع دعم HTTPS.",
    "en": "Web server and reverse proxy with HTTPS."
  },
  "fatedier/frp": {
    "ar": "نفق شبكي للوصول إلى خدمات خلف الشبكات.",
    "en": "Reverse-proxy tunneling for private services."
  },
  "juanfont/headscale": {
    "ar": "خادم تنسيق ذاتي الاستضافة لشبكات Tailscale.",
    "en": "Self-hosted coordination server for Tailscale."
  },
  "keepassxreboot/keepassxc": {
    "ar": "إدارة كلمات المرور داخل خزنة مشفرة محليًا.",
    "en": "Store passwords in an encrypted local vault."
  },
  "bitwarden/clients": {
    "ar": "تطبيقات لإدارة كلمات المرور ومزامنتها.",
    "en": "Password management and syncing clients."
  },
  "cryptomator/cryptomator": {
    "ar": "تشفير الملفات قبل تخزينها سحابيًا.",
    "en": "Encrypt files before cloud storage."
  },
  "filosottile/age": {
    "ar": "أداة بسيطة لتشفير الملفات باستخدام مفاتيح عامة.",
    "en": "Simple public-key file encryption."
  },
  "virustotal/yara": {
    "ar": "مطابقة أنماط الملفات لتحليل البرمجيات والمحتوى.",
    "en": "Pattern-matching rules for file and malware analysis."
  },
  "cisco-talos/clamav": {
    "ar": "محرك مفتوح المصدر لفحص الملفات ضد البرمجيات الضارة.",
    "en": "Open-source antivirus scanning engine."
  },
  "librehardwaremonitor/librehardwaremonitor": {
    "ar": "قراءة حرارة CPU وGPU وحساسات الكمبيوتر.",
    "en": "Read computer temperatures and hardware sensors."
  },
  "gametechdev/presentmon": {
    "ar": "قياس أزمنة الإطارات لتحليل أداء الألعاب.",
    "en": "Capture frame timing for game performance analysis."
  },
  "openhardwaremonitor/openhardwaremonitor": {
    "ar": "أداة مراقبة قديمة نسبيًا لقراءات حساسات الكمبيوتر.",
    "en": "Older hardware sensor monitoring utility."
  },
  "aristocratos/btop": {
    "ar": "مراقبة موارد النظام من نافذة الطرفية.",
    "en": "Terminal-based system resource monitor."
  },
  "grafana/grafana": {
    "ar": "لوحات قياس ورسوم لمراقبة الأنظمة والخدمات.",
    "en": "Dashboards for observability and metrics."
  },
  "prometheus/prometheus": {
    "ar": "جمع مقاييس الخدمات والأنظمة عبر الزمن.",
    "en": "Collect and query time-series metrics."
  },
  "laurent22/joplin": {
    "ar": "تدوين الملاحظات وتنظيمها ومزامنتها.",
    "en": "Note taking and synchronization."
  },
  "logseq/logseq": {
    "ar": "تنظيم ملاحظات وأفكار وروابط بينها.",
    "en": "Linked notes and knowledge organization."
  },
  "sumatrapdfreader/sumatrapdf": {
    "ar": "قارئ سريع وخفيف لملفات PDF والكتب.",
    "en": "Fast lightweight PDF and e-book reader."
  },
  "kovidgoyal/calibre": {
    "ar": "تنظيم مكتبة الكتب الإلكترونية وتحويل الصيغ.",
    "en": "Manage and convert e-book libraries."
  },
  "zotero/zotero": {
    "ar": "إدارة المراجع العلمية والأبحاث والاستشهادات.",
    "en": "Manage research references and citations."
  },
  "cyanfish/naps2": {
    "ar": "مسح المستندات ضوئيًا وحفظها PDF.",
    "en": "Scan documents and save PDFs."
  },
  "torakiki/pdfsam": {
    "ar": "دمج ملفات PDF وتقسيمها وترتيب صفحاتها.",
    "en": "Merge, split and rearrange PDFs."
  },
  "libreoffice/core": {
    "ar": "حزمة مكتبية للمستندات والجداول والعروض.",
    "en": "Office suite for documents, sheets and slides."
  },
  "junegunn/fzf": {
    "ar": "بحث واختيار تفاعلي سريع في الطرفية.",
    "en": "Interactive fuzzy finder in the terminal."
  }
}
