/// Configuration API Raya
class ApiConfig {
  /// URL de base du backend Raya
  static const String baseUrl = 'https://app.raya-ia.fr';

  /// Timeout des requêtes en secondes
  /// receiveTimeout aligné sur le backend Railway (90s).
  /// Nécessaire pour Opus 4.7 + 8192 tokens qui peut prendre 60-90s.
  static const int connectTimeout = 10;
  static const int receiveTimeout = 90;
  static const int sendTimeout = 30;

  /// Polling /chat/history en cas de timeout — parité avec la PWA.
  /// Si /raya timeout, on poll l'historique pour voir si la réponse
  /// est arrivée côté serveur (fire-and-forget du backend).
  static const int historyPollingIntervalMs = 3000;
  static const int historyPollingMaxSeconds = 90;

  /// Endpoints
  static const String loginEndpoint = '/login-app';
  static const String logoutEndpoint = '/logout';
  static const String rayaEndpoint = '/raya';
  static const String speakEndpoint = '/speak';
  static const String feedbackEndpoint = '/raya/feedback';
  static const String bugReportEndpoint = '/raya/bug-report';
  static const String whyEndpoint = '/raya/why';
  static const String historyEndpoint = '/chat/history';
  static const String healthEndpoint = '/health';
  static const String tokenStatusEndpoint = '/token-status';
  static const String topicsEndpoint = '/topics';
  static const String onboardingEndpoint = '/onboarding/status';
  static const String adminUsersEndpoint = '/admin/users';
}
