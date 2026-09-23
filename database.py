from supabase import create_client, Client

SUPABASE_URL = "https://bcqtcrqiuxvilurqptyl.supabase.co"
SUPABASE_KEY = "sb_publishable_Cx57TvH9CVCz8-y2_BURaQ_fowykuO5"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)