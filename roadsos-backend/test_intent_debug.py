from app.services.query_classifier import classify_query

profile = classify_query("tell the top 2 hospital in my location")
print("intent:", profile.intent)
print("tokens:", profile.tokens)
print("needs_location_services:", profile.needs_location_services)
