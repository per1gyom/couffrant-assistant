import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/auth_service.dart';
import '../services/chat_service.dart';
import '../services/tts_service.dart';
import '../services/feedback_service.dart';
import 'login_screen.dart';
import 'topics_sheet.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _authService = AuthService();
  final _chatService = ChatService();
  final _tts = TtsService();
  final _feedback = FeedbackService();
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();
  final _inputFocus = FocusNode();

  List<ChatMessage> _messages = [];
  List<PendingAction> _pendingActions = [];
  AskChoice? _askChoice;
  bool _loading = false;
  bool _historyLoaded = false;
  bool _autoSpeak = true;
  String _username = '';
  final Set<int> _likedIds = {};
  final Set<int> _dislikedIds = {};

  @override
  void initState() {
    super.initState();
    _username = _authService.getUsername() ?? '';
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    try {
      final history = await _chatService.loadHistory();
      if (mounted && history.isNotEmpty) {
        setState(() { _messages = history; _historyLoaded = true; });
        _scrollToBottom(animate: false);
      }
    } catch (_) {}
  }

  Future<void> _sendMessage([String? override]) async {
    final text = override ?? _inputController.text.trim();
    if (text.isEmpty || _loading) return;
    _inputController.clear();
    _tts.stop();
    setState(() {
      _messages.add(ChatMessage(text: text, isUser: true));
      _loading = true; _askChoice = null;
    });
    _scrollToBottom();
    try {
      final response = await _chatService.sendMessage(text);
      var answer = response.answer;
      final speedMatch = RegExp(r'\[SPEAK_SPEED:([\d.]+)\]').firstMatch(answer);
      if (speedMatch != null) _tts.speed = double.tryParse(speedMatch.group(1)!) ?? 1.2;
      answer = answer.replaceAll(RegExp(r'\[ACTION:[A-Z_]+:[^\]]*\]'), '');
      answer = answer.replaceAll(RegExp(r'\[SPEAK_SPEED:[\d.]+\]'), '');
      answer = answer.trim();
      if (mounted) {
        setState(() {
          _messages.add(ChatMessage(text: answer, isUser: false,
            ariaMemoryId: response.ariaMemoryId, modelTier: response.modelTier));
          _pendingActions = response.pendingActions;
          _askChoice = response.askChoice; _loading = false;
        });
        _scrollToBottom();
        if (_autoSpeak && answer.isNotEmpty) _tts.speak(answer);
      }
    } catch (e) {
      if (mounted) setState(() {
        _messages.add(ChatMessage(text: 'Erreur de connexion \u00e0 Raya.', isUser: false));
        _loading = false;
      });
    }
  }

  // --- FEEDBACK HANDLERS ---

  void _onThumbUp(int id) async {
    if (_likedIds.contains(id)) return;
    setState(() { _likedIds.add(id); _dislikedIds.remove(id); });
    final ok = await _feedback.sendPositive(id);
    if (ok && mounted) _showSnack('\ud83d\udc4d Merci pour ton retour !');
  }

  void _onThumbDown(int id, String msgText) {
    if (_dislikedIds.contains(id)) return;
    final ctrl = TextEditingController();
    showDialog(context: context, builder: (ctx) => AlertDialog(
      backgroundColor: const Color(0xFF1A1C24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Text('Qu\'est-ce qui n\'allait pas ?', style: TextStyle(color: Colors.white, fontSize: 16)),
      content: TextField(controller: ctrl, maxLines: 3, style: const TextStyle(color: Colors.white, fontSize: 14),
        decoration: InputDecoration(hintText: 'Optionnel : d\u00e9cris le probl\u00e8me...',
          hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
          filled: true, fillColor: Colors.white.withOpacity(0.07),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none))),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx),
          child: Text('Annuler', style: TextStyle(color: Colors.white.withOpacity(0.5)))),
        TextButton(onPressed: () async {
          Navigator.pop(ctx);
          setState(() { _dislikedIds.add(id); _likedIds.remove(id); });
          final ok = await _feedback.sendNegative(id, comment: ctrl.text.trim());
          if (ok && mounted) _showSnack('\ud83d\udc4e Feedback envoy\u00e9, merci !');
        }, child: const Text('Envoyer', style: TextStyle(color: Color(0xFF22C55E)))),
      ],
    ));
  }

  void _onWhy(int id) async {
    _showSnack('\ud83d\udca1 Chargement...');
    final data = await _feedback.getWhy(id);
    if (!mounted) return;
    if (data == null) { _showSnack('Pas d\'info disponible'); return; }
    showDialog(context: context, builder: (ctx) => AlertDialog(
      backgroundColor: const Color(0xFF1A1C24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Text('\ud83d\udca1 Pourquoi cette r\u00e9ponse ?', style: TextStyle(color: Colors.white, fontSize: 16)),
      content: SingleChildScrollView(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        if (data['model_tier'] != null) _whyRow('Mod\u00e8le', data['model_tier']),
        if (data['tools_used'] != null) _whyRow('Outils', data['tools_used'].toString()),
        if (data['context_sources'] != null) _whyRow('Sources', data['context_sources'].toString()),
        if (data['processing_time'] != null) _whyRow('Temps', '${data['processing_time']}s'),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx),
        child: const Text('OK', style: TextStyle(color: Color(0xFF22C55E))))],
    ));
  }

  Widget _whyRow(String label, String value) {
    return Padding(padding: const EdgeInsets.only(bottom: 8), child: RichText(text: TextSpan(children: [
      TextSpan(text: '$label : ', style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 13)),
      TextSpan(text: value, style: const TextStyle(color: Colors.white, fontSize: 13)),
    ])));
  }

  void _onBugReport(int id, String msgText) {
    final ctrl = TextEditingController();
    String type = 'bug';
    showDialog(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setDialogState) => AlertDialog(
      backgroundColor: const Color(0xFF1A1C24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Text('\ud83d\udc1b Signaler', style: TextStyle(color: Colors.white, fontSize: 16)),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        Row(children: [
          _typeChip('Bug', 'bug', type, (v) => setDialogState(() => type = v)),
          const SizedBox(width: 8),
          _typeChip('Am\u00e9lioration', 'feature', type, (v) => setDialogState(() => type = v)),
        ]),
        const SizedBox(height: 12),
        TextField(controller: ctrl, maxLines: 4, style: const TextStyle(color: Colors.white, fontSize: 14),
          decoration: InputDecoration(hintText: 'D\u00e9cris le probl\u00e8me...',
            hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
            filled: true, fillColor: Colors.white.withOpacity(0.07),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none))),
      ]),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx),
          child: Text('Annuler', style: TextStyle(color: Colors.white.withOpacity(0.5)))),
        TextButton(onPressed: () async {
          if (ctrl.text.trim().isEmpty) return;
          Navigator.pop(ctx);
          // Trouver le message utilisateur precedent
          String? userInput;
          final msgIdx = _messages.indexWhere((m) => m.ariaMemoryId == id);
          if (msgIdx > 0) userInput = _messages[msgIdx - 1].text;
          final reportId = await _feedback.sendBugReport(
            reportType: type, description: ctrl.text.trim(),
            ariaMemoryId: id, userInput: userInput, rayaResponse: msgText);
          if (mounted) _showSnack(reportId != null
            ? '\ud83d\udc1b Rapport #$reportId envoy\u00e9 !' : 'Erreur d\'envoi');
        }, child: const Text('Envoyer', style: TextStyle(color: Color(0xFF22C55E)))),
      ],
    )));
  }

  Widget _typeChip(String label, String value, String current, ValueChanged<String> onTap) {
    final selected = current == value;
    return GestureDetector(onTap: () => onTap(value), child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
      decoration: BoxDecoration(
        color: selected ? const Color(0xFF22C55E).withOpacity(0.2) : Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: selected ? const Color(0xFF22C55E) : Colors.white12)),
      child: Text(label, style: TextStyle(fontSize: 13,
        color: selected ? const Color(0xFF22C55E) : Colors.white54))));
  }

  void _showSnack(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg), duration: const Duration(seconds: 2),
      backgroundColor: const Color(0xFF1A1C24),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))));
  }

  // --- NAVIGATION ---

  void _scrollToBottom({bool animate = true}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      if (animate) _scrollController.animateTo(_scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      else _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
    });
  }

  Future<void> _logout() async {
    _tts.stop(); await _authService.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const LoginScreen()));
  }



  void _showTopics() {
    showModalBottomSheet(context: context, backgroundColor: const Color(0xFF1A1C24),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => TopicsSheet(onTopicTap: (title) {
        _sendMessage('Fais-moi un point sur le sujet "$title"');
      }),
    );
  }
  void _showSpeedSheet() {
    showModalBottomSheet(context: context, backgroundColor: const Color(0xFF1A1C24),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) {
        double localSpeed = _tts.speed;
        return StatefulBuilder(builder: (ctx, setSheetState) => Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 36, height: 4, decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 16),
            const Text('Vitesse de la voix', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500)),
            const SizedBox(height: 20),
            Row(children: [
              const Text('0.5x', style: TextStyle(color: Colors.white38, fontSize: 12)),
              Expanded(child: SliderTheme(data: SliderThemeData(
                activeTrackColor: const Color(0xFF22C55E), inactiveTrackColor: Colors.white12,
                thumbColor: const Color(0xFF22C55E), overlayColor: const Color(0xFF22C55E).withOpacity(0.15), trackHeight: 4),
                child: Slider(value: localSpeed, min: 0.5, max: 2.5, divisions: 20,
                  label: '${localSpeed.toStringAsFixed(1)}x',
                  onChanged: (v) { setSheetState(() => localSpeed = v); setState(() => _tts.speed = v); }))),
              const Text('2.5x', style: TextStyle(color: Colors.white38, fontSize: 12)),
            ]),
            Text('${localSpeed.toStringAsFixed(1)}x', style: const TextStyle(color: Color(0xFF22C55E), fontSize: 24, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            TextButton(onPressed: () { setSheetState(() => localSpeed = 1.2); setState(() => _tts.speed = 1.2); },
              child: Text('R\u00e9initialiser (1.2x)', style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 13))),
          ])));
      });
  }

  @override
  void dispose() { _inputController.dispose(); _scrollController.dispose(); _inputFocus.dispose(); _tts.dispose(); super.dispose(); }

  // --- BUILD ---

  @override
  Widget build(BuildContext context) {
    return Scaffold(backgroundColor: const Color(0xFF0F1117),
      body: SafeArea(child: Column(children: [
        _buildHeader(),
        Divider(height: 1, color: Colors.white.withOpacity(0.08)),
        Expanded(child: _buildMessageList()),
        if (_askChoice != null) _buildAskChoice(),
        if (_pendingActions.isNotEmpty) _buildPendingActions(),
        _buildInputBar(),
      ])));
  }

  Widget _buildHeader() {
    return Padding(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(children: [
        Container(width: 8, height: 8, decoration: const BoxDecoration(color: Color(0xFF22C55E), shape: BoxShape.circle)),
        const SizedBox(width: 8),
        const Text('Raya', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white)),
        const Spacer(),
        // Bouton Sujets
        IconButton(
          icon: Icon(Icons.bookmark_outline, color: Colors.white.withOpacity(0.5), size: 22),
          onPressed: _showTopics, tooltip: 'Sujets'),
        PopupMenuButton<String>(
          icon: Icon(Icons.more_vert, color: Colors.white.withOpacity(0.6)),
          color: const Color(0xFF1A1C24),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          onSelected: (v) {
            if (v == 'logout') _logout();
            if (v == 'autospeak') setState(() => _autoSpeak = !_autoSpeak);
            if (v == 'speed') _showSpeedSheet();
          },
          itemBuilder: (_) => [
            PopupMenuItem(enabled: false, child: Text('Connect\u00e9 : $_username',
              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 13))),
            const PopupMenuDivider(),
            PopupMenuItem(value: 'autospeak', child: Row(children: [
              Icon(_autoSpeak ? Icons.volume_up : Icons.volume_off,
                color: _autoSpeak ? const Color(0xFF22C55E) : Colors.white54, size: 18),
              const SizedBox(width: 10),
              Text(_autoSpeak ? 'AutoSpeak : ON' : 'AutoSpeak : OFF',
                style: TextStyle(color: _autoSpeak ? const Color(0xFF22C55E) : Colors.white54)),
            ])),
            PopupMenuItem(value: 'speed', child: Row(children: [
              Icon(Icons.speed, color: Colors.white.withOpacity(0.6), size: 18),
              const SizedBox(width: 10),
              Text('Vitesse : ${_tts.speed.toStringAsFixed(1)}x', style: TextStyle(color: Colors.white.withOpacity(0.6))),
            ])),
            const PopupMenuDivider(),
            const PopupMenuItem(value: 'logout', child: Row(children: [
              Icon(Icons.logout, color: Color(0xFFEF4444), size: 18), SizedBox(width: 10),
              Text('D\u00e9connexion', style: TextStyle(color: Color(0xFFEF4444))),
            ])),
          ]),
      ]));
  }

  Widget _buildMessageList() {
    if (_messages.isEmpty && !_loading) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 56, height: 56, decoration: BoxDecoration(
          color: const Color(0xFF22C55E).withOpacity(0.15), borderRadius: BorderRadius.circular(16)),
          child: const Center(child: Text('\u2726', style: TextStyle(fontSize: 28, color: Color(0xFF22C55E))))),
        const SizedBox(height: 16),
        const Text('Bonjour ! Comment puis-je t\'aider ?',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: Colors.white)),
      ]));
    }
    return ListView.builder(controller: _scrollController,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      itemCount: _messages.length + (_historyLoaded ? 1 : 0) + (_loading ? 1 : 0),
      itemBuilder: (context, index) {
        if (_historyLoaded && index == 0) {
          return Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Row(children: [
            Expanded(child: Divider(color: Colors.white.withOpacity(0.1))),
            Padding(padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text('conversation pr\u00e9c\u00e9dente', style: TextStyle(fontSize: 11, color: Colors.white.withOpacity(0.25)))),
            Expanded(child: Divider(color: Colors.white.withOpacity(0.1))),
          ]));
        }
        final msgIndex = _historyLoaded ? index - 1 : index;
        if (msgIndex >= _messages.length) return _buildLoadingBubble();
        return _buildMessageBubble(_messages[msgIndex]);
      });
  }

  Widget _buildMessageBubble(ChatMessage msg) {
    final isUser = msg.isUser;
    final initial = _username.isNotEmpty ? _username[0].toUpperCase() : 'U';
    final id = msg.ariaMemoryId;
    return Padding(padding: const EdgeInsets.only(bottom: 10), child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      textDirection: isUser ? TextDirection.rtl : TextDirection.ltr,
      children: [
        Container(width: 30, height: 30, decoration: BoxDecoration(
          color: isUser ? const Color(0xFF1E3A5F) : const Color(0xFF1A3D2A), borderRadius: BorderRadius.circular(10)),
          child: Center(child: Text(isUser ? initial : '\u2726',
            style: TextStyle(fontSize: isUser ? 13 : 15, fontWeight: FontWeight.w600,
              color: isUser ? const Color(0xFF85B7EB) : const Color(0xFF22C55E))))),
        const SizedBox(width: 8),
        Flexible(child: Column(
          crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            Container(padding: const EdgeInsets.all(12), decoration: BoxDecoration(
              color: isUser ? const Color(0xFF1E3A5F).withOpacity(0.5) : Colors.white.withOpacity(0.06),
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(isUser ? 16 : 4), topRight: Radius.circular(isUser ? 4 : 16),
                bottomLeft: const Radius.circular(16), bottomRight: const Radius.circular(16))),
              child: isUser
                ? Text(msg.text, style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.5))
                : MarkdownBody(data: msg.text, styleSheet: MarkdownStyleSheet(
                    p: const TextStyle(color: Colors.white, fontSize: 14, height: 1.5),
                    h1: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                    h2: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                    h3: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                    strong: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                    em: const TextStyle(color: Colors.white, fontStyle: FontStyle.italic),
                    code: TextStyle(color: const Color(0xFF22C55E), backgroundColor: Colors.white.withOpacity(0.08), fontSize: 13),
                    listBullet: const TextStyle(color: Colors.white, fontSize: 14),
                    a: const TextStyle(color: Color(0xFF85B7EB), decoration: TextDecoration.underline)),
                  onTapLink: (text, href, title) {
                    if (href != null) launchUrl(Uri.parse(href), mode: LaunchMode.externalApplication);
                  })),
            if (!isUser && id != null)
              Padding(padding: const EdgeInsets.only(top: 4), child: Row(mainAxisSize: MainAxisSize.min, children: [
                _feedbackBtn('\ud83d\udd0a', null, () { if (_tts.isSpeaking) _tts.stop(); else _tts.speak(msg.text); }),
                _feedbackBtn('\ud83d\udc4d', _likedIds.contains(id) ? const Color(0xFF22C55E) : null, () => _onThumbUp(id)),
                _feedbackBtn('\ud83d\udc4e', _dislikedIds.contains(id) ? const Color(0xFFEF4444) : null, () => _onThumbDown(id, msg.text)),
                _feedbackBtn('\ud83d\udca1', null, () => _onWhy(id)),
                _feedbackBtn('\ud83d\udc1b', null, () => _onBugReport(id, msg.text)),
              ])),
          ],
        )),
      ],
    ));
  }

  Widget _feedbackBtn(String emoji, Color? bg, VoidCallback onTap) {
    return GestureDetector(onTap: onTap, child: Container(
      margin: const EdgeInsets.symmetric(horizontal: 2),
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      decoration: bg != null ? BoxDecoration(color: bg.withOpacity(0.2), borderRadius: BorderRadius.circular(6)) : null,
      child: Text(emoji, style: const TextStyle(fontSize: 16))));
  }

  Widget _buildLoadingBubble() {
    return Padding(padding: const EdgeInsets.only(bottom: 10), child: Row(
      crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(width: 30, height: 30, decoration: BoxDecoration(
          color: const Color(0xFF1A3D2A), borderRadius: BorderRadius.circular(10)),
          child: const Center(child: Text('\u2726', style: TextStyle(fontSize: 15, color: Color(0xFF22C55E))))),
        const SizedBox(width: 8),
        Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.06), borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4), topRight: Radius.circular(16),
            bottomLeft: Radius.circular(16), bottomRight: Radius.circular(16))),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            _dot(0), const SizedBox(width: 4), _dot(1), const SizedBox(width: 4), _dot(2)])),
      ]));
  }

  Widget _dot(int i) {
    return TweenAnimationBuilder<double>(tween: Tween(begin: 0.3, end: 1.0),
      duration: Duration(milliseconds: 600 + i * 200),
      builder: (_, v, __) => Opacity(opacity: v, child: Container(width: 6, height: 6,
        decoration: BoxDecoration(color: Colors.white.withOpacity(0.4), shape: BoxShape.circle))));
  }

  Widget _buildAskChoice() {
    return Container(padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: Wrap(spacing: 8, runSpacing: 8,
        children: _askChoice!.options.map((opt) => OutlinedButton(
          onPressed: () => _sendMessage(opt),
          style: OutlinedButton.styleFrom(foregroundColor: const Color(0xFF22C55E),
            side: const BorderSide(color: Color(0xFF22C55E), width: 0.5),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10)),
          child: Text(opt, style: const TextStyle(fontSize: 13)))).toList()));
  }

  Widget _buildPendingActions() {
    return Container(margin: const EdgeInsets.fromLTRB(12, 4, 12, 4), padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: Colors.white.withOpacity(0.04), borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withOpacity(0.08))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('\u23f8\ufe0f ${_pendingActions.length} action(s) en attente',
          style: TextStyle(fontSize: 12, color: Colors.white.withOpacity(0.5))),
        const SizedBox(height: 6),
        ..._pendingActions.map((a) => Padding(padding: const EdgeInsets.only(bottom: 6),
          child: Row(children: [
            Expanded(child: Text(a.label, style: const TextStyle(color: Colors.white, fontSize: 13))),
            TextButton(onPressed: () => _sendMessage('Confirme l\'action ${a.id}'),
              child: const Text('\u2713', style: TextStyle(color: Color(0xFF22C55E)))),
            TextButton(onPressed: () => _sendMessage('Annule l\'action ${a.id}'),
              child: const Text('\u2717', style: TextStyle(color: Color(0xFFEF4444)))),
          ]))),
      ]));
  }

  Widget _buildInputBar() {
    return Container(padding: const EdgeInsets.fromLTRB(8, 8, 8, 16),
      decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withOpacity(0.08)))),
      child: Row(children: [
        IconButton(icon: Icon(Icons.attach_file, color: Colors.white.withOpacity(0.4)), onPressed: () {}),
        Expanded(child: TextField(controller: _inputController, focusNode: _inputFocus,
          style: const TextStyle(color: Colors.white, fontSize: 14), maxLines: 4, minLines: 1,
          decoration: InputDecoration(hintText: 'Message...', hintStyle: TextStyle(color: Colors.white.withOpacity(0.25)),
            filled: true, fillColor: Colors.white.withOpacity(0.07),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(21), borderSide: BorderSide.none)),
          textInputAction: TextInputAction.send, onSubmitted: (_) => _sendMessage())),
        const SizedBox(width: 8),
        GestureDetector(onTap: () {}, child: Container(width: 44, height: 44,
          decoration: const BoxDecoration(color: Color(0xFF22C55E), shape: BoxShape.circle),
          child: const Icon(Icons.mic, color: Colors.white, size: 22))),
        const SizedBox(width: 6),
        GestureDetector(onTap: _sendMessage, child: Container(width: 36, height: 36,
          decoration: BoxDecoration(color: Colors.white.withOpacity(0.1), shape: BoxShape.circle),
          child: const Icon(Icons.send, color: Colors.white, size: 18))),
      ]));
  }
}
