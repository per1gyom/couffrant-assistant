/// Configuration API Raya
class ApiConfig {
  /// URL de base du backend Raya
  static const String baseUrl = 'https://app.raya-ia.fr';

  /// Timeout des requêtes en secondes
  static const int connectTimeout = 10;
  static const int receiveTimeout = 30;

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
