import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Sujet utilisateur
class Topic {
  final String id;
  String title;
  String status; // active, paused, archived
  DateTime lastAccess;

  Topic({required this.id, required this.title, this.status = 'active', DateTime? lastAccess})
      : lastAccess = lastAccess ?? DateTime.now();

  Map<String, dynamic> toJson() => {
    'id': id, 'title': title, 'status': status,
    'lastAccess': lastAccess.toIso8601String(),
  };

  factory Topic.fromJson(Map<String, dynamic> json) => Topic(
    id: json['id'], title: json['title'], status: json['status'] ?? 'active',
    lastAccess: DateTime.tryParse(json['lastAccess'] ?? '') ?? DateTime.now(),
  );
}

/// Service sujets — stockage local (sera remplace par API quand Opus aura cree les endpoints)
class TopicsService {
  static const _storageKey = 'raya_topics';
  static const _titleKey = 'raya_topics_title';
  final _storage = const FlutterSecureStorage();

  /// Titre de la section (personnalisable)
  Future<String> getSectionTitle() async {
    return await _storage.read(key: _titleKey) ?? 'Mes sujets';
  }

  Future<void> setSectionTitle(String title) async {
    await _storage.write(key: _titleKey, value: title);
  }

  /// Liste des sujets
  Future<List<Topic>> getTopics() async {
    final raw = await _storage.read(key: _storageKey);
    if (raw == null || raw.isEmpty) return [];
    try {
      final list = jsonDecode(raw) as List;
      final topics = list.map((e) => Topic.fromJson(e)).toList();
      topics.sort((a, b) => b.lastAccess.compareTo(a.lastAccess));
      return topics;
    } catch (_) { return []; }
  }

  Future<void> _saveTopics(List<Topic> topics) async {
    await _storage.write(key: _storageKey, value: jsonEncode(topics.map((t) => t.toJson()).toList()));
  }

  /// Creer un sujet
  Future<Topic> createTopic(String title) async {
    final topics = await getTopics();
    final topic = Topic(id: DateTime.now().millisecondsSinceEpoch.toString(), title: title);
    topics.insert(0, topic);
    await _saveTopics(topics);
    return topic;
  }

  /// Modifier un sujet
  Future<void> updateTopic(String id, {String? title, String? status}) async {
    final topics = await getTopics();
    final idx = topics.indexWhere((t) => t.id == id);
    if (idx == -1) return;
    if (title != null) topics[idx].title = title;
    if (status != null) topics[idx].status = status;
    await _saveTopics(topics);
  }

  /// Marquer comme accede (remonte en haut)
  Future<void> touch(String id) async {
    final topics = await getTopics();
    final idx = topics.indexWhere((t) => t.id == id);
    if (idx == -1) return;
    topics[idx].lastAccess = DateTime.now();
    await _saveTopics(topics);
  }

  /// Supprimer un sujet
  Future<void> deleteTopic(String id) async {
    final topics = await getTopics();
    topics.removeWhere((t) => t.id == id);
    await _saveTopics(topics);
  }
}
