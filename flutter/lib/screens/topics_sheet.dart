import 'package:flutter/material.dart';
import '../services/topics_service.dart';

/// Bottom sheet des sujets/projets
/// Tap sur un sujet → envoie "Fais-moi un point sur [sujet]" a Raya
class TopicsSheet extends StatefulWidget {
  final void Function(String topicTitle) onTopicTap;
  const TopicsSheet({super.key, required this.onTopicTap});
  @override
  State<TopicsSheet> createState() => _TopicsSheetState();
}

class _TopicsSheetState extends State<TopicsSheet> {
  final _service = TopicsService();
  List<Topic> _topics = [];
  String _sectionTitle = 'Mes sujets';
  bool _loading = true;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final topics = await _service.getTopics();
    final title = await _service.getSectionTitle();
    if (mounted) setState(() { _topics = topics; _sectionTitle = title; _loading = false; });
  }

  void _addTopic() {
    final ctrl = TextEditingController();
    showDialog(context: context, builder: (ctx) => AlertDialog(
      backgroundColor: const Color(0xFF1A1C24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Text('Nouveau sujet', style: TextStyle(color: Colors.white, fontSize: 16)),
      content: TextField(controller: ctrl, autofocus: true,
        style: const TextStyle(color: Colors.white, fontSize: 14),
        decoration: InputDecoration(hintText: 'Ex: Process de devis',
          hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
          filled: true, fillColor: Colors.white.withOpacity(0.07),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none))),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx),
          child: Text('Annuler', style: TextStyle(color: Colors.white.withOpacity(0.5)))),
        TextButton(onPressed: () async {
          if (ctrl.text.trim().isEmpty) return;
          Navigator.pop(ctx);
          await _service.createTopic(ctrl.text.trim());
          _load();
        }, child: const Text('Cr\u00e9er', style: TextStyle(color: Color(0xFF22C55E)))),
      ],
    ));
  }

  void _editTitle() {
    final ctrl = TextEditingController(text: _sectionTitle);
    showDialog(context: context, builder: (ctx) => AlertDialog(
      backgroundColor: const Color(0xFF1A1C24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Text('Titre de la section', style: TextStyle(color: Colors.white, fontSize: 16)),
      content: TextField(controller: ctrl, autofocus: true,
        style: const TextStyle(color: Colors.white, fontSize: 14),
        decoration: InputDecoration(hintText: 'Mes projets, Mes dossiers...',
          hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
          filled: true, fillColor: Colors.white.withOpacity(0.07),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none))),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx),
          child: Text('Annuler', style: TextStyle(color: Colors.white.withOpacity(0.5)))),
        TextButton(onPressed: () async {
          if (ctrl.text.trim().isEmpty) return;
          Navigator.pop(ctx);
          await _service.setSectionTitle(ctrl.text.trim());
          _load();
        }, child: const Text('OK', style: TextStyle(color: Color(0xFF22C55E)))),
      ],
    ));
  }

  void _editTopic(Topic topic) {
    final ctrl = TextEditingController(text: topic.title);
    showDialog(context: context, builder: (ctx) => AlertDialog(
      backgroundColor: const Color(0xFF1A1C24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Text('Modifier le sujet', style: TextStyle(color: Colors.white, fontSize: 16)),
      content: TextField(controller: ctrl, autofocus: true,
        style: const TextStyle(color: Colors.white, fontSize: 14),
        decoration: InputDecoration(filled: true, fillColor: Colors.white.withOpacity(0.07),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none))),
      actions: [
        TextButton(onPressed: () async {
          Navigator.pop(ctx);
          await _service.deleteTopic(topic.id);
          _load();
        }, child: const Text('Supprimer', style: TextStyle(color: Color(0xFFEF4444)))),
        TextButton(onPressed: () => Navigator.pop(ctx),
          child: Text('Annuler', style: TextStyle(color: Colors.white.withOpacity(0.5)))),
        TextButton(onPressed: () async {
          if (ctrl.text.trim().isEmpty) return;
          Navigator.pop(ctx);
          await _service.updateTopic(topic.id, title: ctrl.text.trim());
          _load();
        }, child: const Text('OK', style: TextStyle(color: Color(0xFF22C55E)))),
      ],
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.6),
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 36, height: 4, decoration: BoxDecoration(
          color: Colors.white24, borderRadius: BorderRadius.circular(2))),
        const SizedBox(height: 12),
        Row(children: [
          GestureDetector(onTap: _editTitle, child: Row(children: [
            Text(_sectionTitle, style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
            const SizedBox(width: 6),
            Icon(Icons.edit, size: 14, color: Colors.white.withOpacity(0.3)),
          ])),
          const Spacer(),
          GestureDetector(onTap: _addTopic, child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(color: const Color(0xFF22C55E).withOpacity(0.15),
              borderRadius: BorderRadius.circular(16)),
            child: const Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.add, size: 16, color: Color(0xFF22C55E)),
              SizedBox(width: 4),
              Text('Ajouter', style: TextStyle(color: Color(0xFF22C55E), fontSize: 13)),
            ]),
          )),
        ]),
        const SizedBox(height: 16),
        if (_loading) const Center(child: CircularProgressIndicator(color: Color(0xFF22C55E)))
        else if (_topics.isEmpty)
          Padding(padding: const EdgeInsets.symmetric(vertical: 32),
            child: Text('Aucun sujet. Ajoute ton premier projet !',
              style: TextStyle(color: Colors.white.withOpacity(0.3), fontSize: 14)))
        else Expanded(child: ListView.builder(
          shrinkWrap: true, itemCount: _topics.length,
          itemBuilder: (ctx, i) {
            final t = _topics[i];
            return ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 4),
              leading: Container(width: 36, height: 36, decoration: BoxDecoration(
                color: const Color(0xFF22C55E).withOpacity(0.1), borderRadius: BorderRadius.circular(10)),
                child: const Center(child: Text('\u2726', style: TextStyle(fontSize: 16, color: Color(0xFF22C55E))))),
              title: Text(t.title, style: const TextStyle(color: Colors.white, fontSize: 14)),
              subtitle: Text(_timeAgo(t.updatedAt),
                style: TextStyle(color: Colors.white.withOpacity(0.3), fontSize: 11)),
              trailing: GestureDetector(onTap: () => _editTopic(t),
                child: Icon(Icons.more_horiz, color: Colors.white.withOpacity(0.3), size: 20)),
              onTap: () {
                _service.touch(t.id);
                Navigator.pop(context);
                widget.onTopicTap(t.title);
              },
            );
          },
        )),
      ]),
    );
  }

  String _timeAgo(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 60) return 'il y a ${diff.inMinutes} min';
    if (diff.inHours < 24) return 'il y a ${diff.inHours}h';
    if (diff.inDays < 7) return 'il y a ${diff.inDays}j';
    return '${dt.day}/${dt.month}/${dt.year}';
  }
}
