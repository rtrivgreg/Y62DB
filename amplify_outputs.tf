output "amplify_app_id" {
  description = "Amplify Hosting app ID."
  value       = aws_amplify_app.bindings_ui.id
}

output "amplify_default_domain" {
  description = "Amplify Hosting's generated *.amplifyapp.com domain for this app."
  value       = aws_amplify_app.bindings_ui.default_domain
}

output "amplify_main_branch_url" {
  description = "Live production URL for the main branch."
  value       = "https://${aws_amplify_branch.main.branch_name}.${aws_amplify_app.bindings_ui.default_domain}"
}
