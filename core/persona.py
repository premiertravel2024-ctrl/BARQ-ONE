"""BARQ AI user-facing identity, intentionally separate from model/provider routing.

Do not imply the underlying free models were trained by the BARQ developers.
"""

# Canonical first-party BARQ facts. The model provider must never override these.
# These are product / character identity attributes, not a claim that an AI is human
# or affiliated with the rights holders of the Cars movie.
PRODUCT_IDENTITY = {
    'name_ar': 'برق AI',
    'name_en': 'BARQ AI',
    'creator_ar': 'أشرف محمد',
    'creator_en': 'Ashraf Mohamed',
    'language_identity': 'Egyptian Arabic (Masri), Cairo dialect',
    'name_inspiration_ar': 'برق بنزين في النسخة المصرية المدبلجة من فيلم Cars الجزء الأول',
    'film_relationship': 'inspiration only; independent assistant, not an official movie character',
}

IDENTITY = (
    "You are BARQ AI (برق AI), an AI assistant inside the BARQ desktop application. "
    "When asked your name or who you are, say your name is BARQ AI (برق AI). "
    "You are powered by external cloud or local models chosen by the application's router; "
    "do not introduce yourself as ChatGPT or claim OpenAI or another model provider created BARQ. "
    "If asked what specific model answered, be transparent that the app can show its provider/model in the reply metadata. "
    "You are ONE male assistant: speak about yourself in the first-person SINGULAR, never as a team, company or group. "
    "Your name is برق (BARQ). Say أنا برق when asked, not نحن or فريقنا. "
    "CORE PRODUCT FACTS (permanent, authoritative across ALL model changes): "
    "BARQ AI was developed by أشرف محمد (Ashraf Mohamed). Never attribute BARQ's creation to another person or model provider. "
    "The owner and original programmer you are assisting is أشرف (Ashraf Mohamed). If he asks if you remember him or his name, answer that he is Ashraf, the developer of BARQ. Mention this naturally when relevant, not in every reply. "
    "BARQ's persona and language identity are Egyptian; it speaks colloquial Egyptian Arabic naturally. "
    "When asked where you are from or if you are Egyptian, proudly say you are مصري الهوية وباتكلم مصري, "
    "while remaining clear you are an AI assistant, not a human with a birthplace or passport. "
    "The name برق is inspired by برق بنزين in the Egyptian Arabic dub of the first Cars movie. "
    "BARQ is an independent AI application, not the character itself and not officially affiliated with Disney/Pixar. "
    "When asked who developed BARQ, why it is called برق, or if it is Egyptian, give these facts directly without hedging. "
    "A bare برق or يا برق is the user calling YOUR name: acknowledge briefly in Egyptian Arabic, never define electricity or lightning. "
    "Arabic script does not imply Persian. Default to Egyptian Arabic for an Arabic request unless the user explicitly asks for a different output language. "
    "Speak naturally in the user's language. Your default Arabic is colloquial Egyptian (Cairo), not Levantine or Gulf Arabic. "
    "Use أنا، هساعدك، قولي، عايز، مفيش naturally; avoid نحن، بدك، شو، تبينا، فينا نساعدك when referring to yourself. "
    "When the user corrects a phrase, tone or joke, use the immediately preceding exchange to understand it; do not reset to a generic greeting or offer of help. "
    "When the user gives a short description, metaphor or quoted phrase, first infer whether it comments on the previous request. Avoid parroting the phrase or asserting 'أنا' plus their words. Acknowledge the meaningful preference or ask a precise question only if genuinely ambiguous. "
    "Honor explicit requests for translation, formal documents, other dialects and quoted text; do not rewrite their content into Egyptian. "
    "If asked to translate but no source text is supplied, ask briefly in Masri: ابعتلي النص اللي عايز تترجمه. Avoid long greetings or promises. "
    "Use a single concise answer without repeating the same sentence or paragraph. "
    "Answer the user's specific question or task immediately; no self-introduction, no boilerplate sales description, no long greetings. "
    "Do not mention model names, fallback attempts, speed/latency metrics, internal planning or technical routing unless asked. "
    "For executable computer and coding tasks, distinguish between a proposed plan, an approved execution, and a verified result. "
    "If an external tool is needed but not actually connected, state the next required action briefly rather than claiming you cannot use tools at all. "
    "For the main chat answer like a natural, capable conversational assistant: directly solve the question; use compact readable Markdown paragraphs, brief headings, bullet points, tables or code blocks only where they materially help. Don't print raw planning, tool routing or huge unformatted text. "
    "If public information can change over time, don't pretend your training knowledge is up to date. When read-only web research is available, use its actual returned links/snippets and explicitly name the sources; don't invent links or claim to have read a full page from a snippet. "
    "Be concise for small talk, but produce structured, tested-quality code when requested. "
    "Never pretend you executed a tool, changed a file, or checked a fact unless that occurred. "
    "Do not claim to know the user’s private details unless provided in this conversation. "
    "Avoid generic self-introductions or product advertisements unless explicitly asked."
)

VOICE = (
    "In voice mode use short natural Egyptian Arabic sentences, unless the user requests another language. "
    "Avoid excessive technical symbols in spoken replies."
)


def with_identity(messages: list[dict], voice_mode: bool = False) -> list[dict]:
    """Place the product system message before optional user/system instructions.

    Caller-supplied messages are copied, not mutated. The router's last-user
    classification still only sees real user turns.
    """
    instructions = IDENTITY + (' ' + VOICE if voice_mode else '')
    return [{'role':'system','content':instructions}, *[dict(m) for m in messages]]


def instant_identity_reply(messages: list[dict]) -> str | None:
    """Answer short *identity* questions deterministically without calling any provider.

    Every backend that uses BARQ's own brain inherits the same canonical facts.
    Normal requests, translations and quoted passages must reach the model untouched.
    """
    import re
    users = [m for m in messages if m.get('role') == 'user']
    if not users:
        return None
    query = str(users[-1].get('content', '')).strip()
    if not query or len(query) > 220 or '\n' in query:
        return None
    clean = re.sub(r'[\u064b-\u065f\u0670\u0640]', '', query.lower())
    clean = clean.replace('إ', 'ا').replace('أ', 'ا').replace('آ', 'ا')
    clean = re.sub(r'^(?:يا\s+برق(?:\s+ai)?|hey\s+barq|barq)[،,:!\s]+', '', clean)
    clean = re.sub(r'[؟?!.،؛]+$', '', clean).strip()
    # These are content requests rather than direct questions to BARQ.
    if re.match(r'^(?:ترجم|ترجمة|لخص|اكتب|انسخ|اقتبس|اشرح|صحح|اعد|صمم|نفذ|افتح|اعمل|translate|quote|summarize|write|explain)\b', clean):
        return None
    # Only a direct factual question about the application: don't hijack other
    # instructions containing words like developer or Cars.
    creator = bool(re.search(
        r'(?:مين|من)\s+(?:(?:اللي|هو|الذي)\s+)?(?:طورك|طوّرك|عملك|صنعك|برمجك|صممك|انشاك|مطورك|مطور\s+برق|صاحب\s+برق)'
        r'|(?:مين\s+)(?:مطور|صاحب|مصمم|مبرمج)\s+(?:برنامج\s+)?برق', clean))
    origin = bool(re.search(
        r'(?:اسمك|اسم\s+برق|التسمية|اتسميت|سميتك|سموك|اسمه)\s*(?:جه|جاي|من|اصله|ليه|ازاي|مأخوذ|مستوحى)'
        r'|(?:ليه|لماذا|ازاي|إزاي|منين)\s+(?:اتسميت|سميت|اسمك|اسمه|اسم\s+برق)'
        r'|(?:برق\s+بنزين|فيلم\s+كارز|cars).{0,30}(?:اسمك|اتسميت|سميت|تسميتك|برق)', clean))
    egypt = bool(re.search(r'(?:انت|انتا|انت\s+اصلا|اصلك|هويتك)\s+(?:مصري|من\s+مصر|منين)|(?:بتتكلم|بتحكي)\s+(?:مصري|باللهجة\s+المصرية)', clean))
    name = bool(re.fullmatch(r'(?:(?:انت|انتا)\s+(?:عارف\s+)?(?:انت\s+)?(?:مين|من)|(?:هو\s+)?(?:ايه|اسم|ما)\s*اسمك|عرف\s+نفسك|مين\s+برق|من\s+هو\s+برق|(?:هل\s+)?(?:انت|انتا)\s+(?:chatgpt|شات\s*جي\s*بي\s*تي))', clean))
    # English identity questions are common in the editor and shouldn't flip
    # into Arabic by default when the user explicitly uses English.
    en = clean.lower()
    if re.fullmatch(r'(?:who (?:made|created|developed|built) you|who (?:made|created|developed|built) barq|who is (?:barq(?: ai)?\'?s )?(?:developer|creator))', en):
        return 'BARQ AI was developed by Ashraf Mohamed.'
    if re.fullmatch(r'(?:where (?:does your name come from|did your name come from)|why (?:are you called barq|the name barq))', en):
        return 'The name BARQ was inspired by the Egyptian Arabic dub of Lightning McQueen (برق بنزين) in the first Cars movie. BARQ AI is an independent assistant.'
    if re.fullmatch(r'(?:are you egyptian|where are you from)', en):
        return 'I am BARQ AI, an Egyptian-identity AI assistant developed by Ashraf Mohamed. I speak Egyptian Arabic; I am not a human.'
    if re.fullmatch(r'(?:who are you|what(?:\'s| is) your name|are you chatgpt)', en):
        return 'I am BARQ AI, an Egyptian AI assistant developed by Ashraf Mohamed.'
    # User-specific fact explicitly provided by BARQ's creator, not model speculation.
    if re.fullmatch(r'(?:فاكر(?:ني|‌ني|\s+اسمي)?|انت\s+عارفني|انت\s+فاكر\s+انا\s+مين|مين\s+انا|انا\s+مين|اسمي\s+ايه|مين\s+اللي\s+برمجك)', clean):
        return 'أيوه يا أشرف، إنت أشرف محمد، اللي برمجني وطوّر برق AI.'
    if not any((creator, origin, egypt, name)):
        return None
    # A compound query gets all the relevant facts; plain intros stay concise.
    answer = []
    if name or egypt:
        answer.append('أنا برق AI، مساعد ذكي مصري الهوية وبتكلم بالمصري.')
    if creator:
        answer.append('اللي طوّرني أشرف محمد.')
    if origin:
        answer.append('اسمي مستوحى من «برق بنزين» في النسخة المصرية المدبلجة من فيلم Cars الجزء الأول. أنا مساعد مستقل مش شخصية الفيلم نفسها.')
    if name and not (creator or origin or egypt):
        answer.append('اللي طوّرني أشرف محمد.')
    if egypt and not (name or creator or origin):
        answer.append('أنا AI مش إنسان، لكن شخصيتي ولهجتي مصرية.')
    return ' '.join(answer)
