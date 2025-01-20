from astrapy import DataAPIClient

# Initialize the client
client = DataAPIClient("AstraCS:wmFkfxfCCwDYPZFStousOBeP:38b8f504c9ebe6a747750d87a302d7d5ae000a05ba7612b07410b562ba3c463")
db = client.get_database_by_api_endpoint(
  "https://dfad9286-9c2b-4713-9c5a-709d9615cbcd-us-east-2.apps.astra.datastax.com"
)

print(f"Connected to Astra DB: {db.list_collection_names()}")

# import openai

# openai.api_key = "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"

# # client = OpenAI()

# completion = openai.ChatCompletion.create(
#     model="gpt-4o-mini",
#     messages=[
#         {"role": "developer", "content": "You are a helpful assistant."},
#         {
#             "role": "user",
#             "content": "what are the starting lyrics for ek pal ka jeena song."
#         }
#     ]
# )

# print(completion.choices[0].message)

# # client = AzureOpenAI(api_key=os.getenv('AZURE_OPENAI_KEY'),
# # api_version=os.getenv('AZURE_OPENAI_API_VERSION'))
# # import redis
# # import time

# # # Load environment variables
# # load_dotenv()

# # # Test AstraDB Connection
# # def test_astra_connection():
# #     try:
# #         astra_client = AstraDB(
# #             token=os.getenv('ASTRA_DB_TOKEN'),
# #             api_endpoint=os.getenv('ASTRA_DB_ENDPOINT')
# #         )
# #         # Simple query to check if AstraDB is connected and working
# #         collection = astra_client.collection(os.getenv('ASTRA_COLLECTION_NAME'))
# #         result = collection.find({'limit': 1})  # Simple query to fetch one document
# #         if result:
# #             print("AstraDB connection is working!")
# #         else:
# #             print("No data found in AstraDB collection.")
# #     except Exception as e:
# #         print(f"AstraDB connection failed: {e}")

# # def test_azure_openai_connection():
# #     try:
# #         # Setup Azure OpenAI client
# #         # TODO: The 'openai.api_base' option isn't read in the client API. You will need to pass it when you instantiate the client, e.g. 'OpenAI(base_url=os.getenv('AZURE_OPENAI_ENDPOINT'))'
# #         # openai.api_base = os.getenv('AZURE_OPENAI_ENDPOINT')

# #         # Using the new OpenAI API interface (v1.0.0+)
# #         response = client.chat.completions.create(model="gpt-3.5-turbo",  # Use the correct model
# #         messages=[{"role": "user", "content": "Hello, world!"}])
# #         print("Azure OpenAI connection is working!")
# #         print(f"Response: {response.choices[0].message.content}")
# #     except Exception as e:
# #         print(f"Azure OpenAI connection failed: {e}")

# # # Test Redis Connection
# # def test_redis_connection():
# #     try:
# #         redis_url = os.getenv('REDIS_URL')
# #         redis_client = redis.from_url(redis_url)

# #         # Test setting and getting a value
# #         redis_client.set('test_key', 'test_value')
# #         value = redis_client.get('test_key')
# #         if value and value.decode() == 'test_value':
# #             print("Redis connection is working!")
# #         else:
# #             print("Redis connection failed to set/get value.")
# #     except Exception as e:
# #         print(f"Redis connection failed: {e}")

# # # Run all tests
# # def test_connections():
# #     print("Testing connections...\n")
# #     test_astra_connection()
# #     print("\n")
# #     test_azure_openai_connection()
# #     print("\n")
# #     test_redis_connection()

# # # Run the tests
# # if __name__ == "__main__":
# #     test_connections()
