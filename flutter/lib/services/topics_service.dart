import '../config/api_config.dart';
import 'api_service.dart';

/// Sujet utilisateur
class Topic {
  final int id;
  String title;
  String status;
  DateTime updatedAt;

  Topic({required this.id, required this.title, this.status = 'active', DateTime? updatedAt})
      : updatedAt = updatedAt ?? DateTime.now();

  factory Topic.fromJson(Map<String, dynamic> json) => Topic(
    id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
    title: json['title'] ?? '',
    status: json['status'] ?? 'active',
    updatedAt: DateTime.tryParse(json['updated_at'] ?? json['created_at'] ?? '') ?? DateTime.now(),
  );
}

/// Service sujets — API backend (endpoints live)
class TopicsService {
  final ApiService _api = ApiService.instance;

  /// Titre de la section (personnalisable)
  Future<String> getSectionTitle() async {
    try {
      final r = await _api.get(ApiConfig.topicsEndpoint);
      if (r.statusCode == 200 && r.data is Map) {
        return r.data['section_title'] ?? 'Mes sujets';
      }
    } catch (_) {}
    return 'Mes sujets';
  }

  Future<void> setSectionTitle(String title) async {
    try {
      await _api.postJson('${ApiConfig.topicsEndpoint}/settings', {'section_title': title});
    } catch (_) {}
  }

  /// Liste des sujets
  Future<List<Topic>> getTopics() async {
    try {
      final r = await _api.get(ApiConfig.topicsEndpoint);
      if (r.statusCode == 200 && r.data is Map && r.data['topics'] is List) {
        final list = (r.data['topics'] as List)
            .map((e) => Topic.fromJson(e as Map<String, dynamic>))
            .toList();
        list.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
        return list;
      }
    } catch (_) {}
    return [];
  }

  /// Creer un sujet
  Future<Topic?> createTopic(String title) async {
    try {
      final r = await _api.postJson(ApiConfig.topicsEndpoint, {'title': title});
      if (r.statusCode == 200 && r.data is Map) {
        return Topic.fromJson(r.data as Map<String, dynamic>);
      }
    } catch (_) {}
    return null;
  }

  /// Modifier un sujet
  Future<void> updateTopic(int id, {String? title, String? status}) async {
    try {
      final body = <String, dynamic>{};
      if (title != null) body['title'] = title;
      if (status != null) body['status'] = status;
      await _api.dio.patch('${ApiConfig.topicsEndpoint}/$id', data: body);
    } catch (_) {}
  }

  /// Marquer comme accede (touch = update sans changement, remonte updated_at)
  Future<void> touch(int id) async {
    // Pas d'endpoint "touch" — on fait un PATCH status=active pour refresh updated_at
    await updateTopic(id, status: 'active');
  }

  /// Supprimer un sujet
  Future<void> deleteTopic(int id) async {
    try {
      await _api.dio.delete('${ApiConfig.topicsEndpoint}/$id');
    } catch (_) {}
  }
}
