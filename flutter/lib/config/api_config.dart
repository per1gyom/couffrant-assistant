/// Configuration API Raya.
/// Base URL et constantes partagées par tous les services.
class ApiConfig {
  /// URL de production Raya
  static const String baseUrl = 'https://app.raya-ia.fr';

  /// Timeout des requêtes HTTP (secondes)
  static const int connectTimeout = 10;
  static const int receiveTimeout = 30;

  /// Taille max fichier (10 Mo)
  static const int maxFileSize = 10 * 1024 * 1024;

  /// Nombre de messages historique par chargement
  static const int historyPageSize = 20;

  /// Vitesse TTS par défaut
  static const double defaultSpeakSpeed = 1.2;
  static const double minSpeakSpeed = 0.5;
  static const double maxSpeakSpeed = 2.5;
}
