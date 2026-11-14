import 'package:flutter_test/flutter_test.dart';
import 'package:__PROJECT_NAME__/app/app.dart';

void main() {
  testWidgets('starter app shows its ready state', (tester) async {
    await tester.pumpWidget(const StudentApp());

    expect(find.text('Your project is ready'), findsOneWidget);
    expect(find.text('Ask your coding agent to build the first feature here.'), findsOneWidget);
  });
}
