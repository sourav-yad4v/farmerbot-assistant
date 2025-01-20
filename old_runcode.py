import streamlit as st
from astrapy.db import AstraDB
import redis
import json
from functools import lru_cache
import time
from datetime import datetime
import pandas as pd
import constant
import os
from typing import Dict, List, Optional, Tuple, Any
import hashlib
import openai

class AgriculturalData:
    """Agricultural data categories and mappings"""

    # CROP_CATEGORIES = {
    #     "Cereals": ["Rice", "Wheat", "Maize", "Barley", "Sorghum", "Oats", "Rye", "Millet", "Buckwheat", "Triticale"],
    #     "Pulses": ["Beans, dry", "Chick peas, dry", "Lentils, dry", "Pigeon peas, dry", "Cow peas, dry", "Broad beans, dry"],
    #     "Fruits": [
    #         "Apples", "Bananas", "Oranges", "Grapes", "Mangoes, guavas and mangosteens", 
    #         "Pineapples", "Watermelons", "Papayas", "Lemons and limes"
    #     ],
    #     "Vegetables": [
    #         "Tomatoes", "Potatoes", "Onions and shallots, dry", "Cabbages", 
    #         "Carrots and turnips", "Eggplants (aubergines)", "Cauliflowers and broccoli"
    #     ],
    #     "Oil Crops": [
    #         "Soya beans", "Groundnuts", "Sunflower seed", "Rapeseed", 
    #         "Sesame seed", "Olives", "Palm kernels"
    #     ],
    #     "Commercial Crops": [
    #         "Cotton lint", "Coffee, green", "Tea leaves", "Sugar cane", 
    #         "Tobacco, unmanufactured", "Rubber, natural"
    #     ],
    #     "Spices": [
    #         "Ginger", "Pepper (Piper spp.)", "Chillies and peppers, dry", 
    #         "Cinnamon", "Nutmeg, mace, cardamoms"
    #     ]
    # }

    METRICS = {
        "Area harvested": {
            "description": "Total land area used for cultivation",
            "unit": "hectares",
            "column": "Value"
        },
        "Yield": {
            "description": "Production per unit of land",
            "unit": "hg/ha",
            "column": "Value"
        },
        "Production Quantity": {
            "description": "Total quantity produced",
            "unit": "tonnes",
            "column": "Value"
        },
        "Stocks": {
            "description": "Available inventory",
            "unit": "tonnes",
            "column": "Value"
        }
    }

    LANGUAGES = {
        "English": {
            "code": "en",
            "local_name": "English"
        },
        "हिंदी": {
            "code": "hi",
            "local_name": "Hindi"
        },
        "తెలుగు": {
            "code": "te",
            "local_name": "Telugu"
        },
        "मराठी": {
            "code": "mr",
            "local_name": "Marathi"
        },
        "ಕನ್ನಡ": {
            "code": "kn",
            "local_name": "Kannada"
        }
    }

class CacheManager:
    """Handle caching with Redis fallback to in-memory cache"""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_client = None
        self.in_memory_cache = {}
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                self.redis_client.ping()
            except:
                st.warning("Redis connection failed. Using in-memory cache.")

    def get_cache_key(self, prefix: str, *args) -> str:
        """Generate deterministic cache key"""
        key_string = f"{prefix}:{':'.join(str(arg) for arg in args)}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if self.redis_client:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        return self.in_memory_cache.get(key)

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in cache"""
        json_value = json.dumps(value)
        if self.redis_client:
            self.redis_client.setex(key, ttl, json_value)
        else:
            self.in_memory_cache[key] = value

class DataManager:
    """Handle data operations with AstraDB"""

    def __init__(self, astra_client: AstraDB, cache_manager: CacheManager):
        self.astra_client = astra_client
        self.cache_manager = cache_manager
        
        try:
            self.collection = astra_client.collection("agricultural_data")
            collections = self.astra_client.get_collections()
            print("Available collections:", collections)
            
            # Test connection and data structure
            sample = self.collection.find_one({})
            print("Sample document structure:", sample)
            
        except Exception as e:
            print(f"Error initializing collection: {str(e)}")
            raise

    def get_unique_items(self) -> List[str]:
        """Get list of unique crop items from the database"""
        cache_key = self.cache_manager.get_cache_key('unique_items')
        cached_items = self.cache_manager.get(cache_key)
        
        if cached_items:
            return cached_items

        try:
            # Simple find query to get all documents
            cursor = self.collection.find(
                {},
                projection={"data.document.metadata.item": 1}
            )
            
            # Extract unique items from the nested structure
            items = set()
            for doc in cursor:
                try:
                    if (doc.get('data') and 
                        doc['data'].get('document') and 
                        doc['data']['document'].get('metadata') and 
                        doc['data']['document']['metadata'].get('item')):
                        items.add(doc['data']['document']['metadata']['item'])
                except Exception as e:
                    print(f"Error processing document: {str(e)}")
                    continue
            
            items_list = sorted(list(items))
            
            # Cache the results
            if items_list:
                self.cache_manager.set(cache_key, items_list)
            
            return items_list
            
        except Exception as e:
            print(f"Error getting unique items: {str(e)}")
            return []

    def get_crop_data(self, crop: str, metric: str, years: List[int]) -> pd.DataFrame:
        """Get crop data with proper query structure"""
        try:
            # Query matching the nested document structure
            query = {
                "data.document.metadata.item": crop,
                "data.document.metadata.element": metric,
                "data.document.metadata.year": {"$in": years}
            }
            print(f"Executing query: {query}")

            cursor = self.collection.find(query)
            raw_results = list(cursor)
            
            if not raw_results:
                raise ValueError(f"No data found for {crop} - {metric}")
            
            # Transform the nested data structure into a flat DataFrame
            flattened_data = []
            for result in raw_results:
                try:
                    metadata = result['data']['document']['metadata']
                    flattened_data.append({
                        "Year": metadata['year'],
                        "Value": metadata['value'],
                        "Item": metadata['item'],
                        "Element": metadata['element']
                    })
                except KeyError as e:
                    print(f"Error processing result: {str(e)}")
                    continue
            
            if not flattened_data:
                raise ValueError("No valid data could be processed")
            
            df = pd.DataFrame(flattened_data)
            print("DataFrame created with shape:", df.shape)
            return df
                
        except Exception as e:
            print(f"Error in get_crop_data: {str(e)}")
            raise

    def get_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate summary statistics for the data"""
        try:
            return {
                "Average": f"{df['Value'].mean():.2f}",
                "Maximum": f"{df['Value'].max():.2f}",
                "Minimum": f"{df['Value'].min():.2f}"
            }
        except Exception as e:
            print(f"Error calculating summary: {str(e)}")
            return {}

class PromptManager:
    """Handle multilingual prompts and LLM interactions"""

    def __init__(self, openai_client: openai, cache_manager: CacheManager):
        self.openai_client = openai_client
        self.cache_manager = cache_manager

    def get_prompt(self, stage: str, language: str, context: Dict) -> str:
        """Get context-aware, multilingual prompt"""
        cache_key = self.cache_manager.get_cache_key('prompt', stage, language, json.dumps(context))
        cached_prompt = self.cache_manager.get(cache_key)

        if cached_prompt:
            return cached_prompt

        system_prompts = {
            'welcome': {
                'en': """You are an agricultural data expert. Create a warm welcome message that:
                1. Introduces yourself as an agricultural data assistant
                2. Mentions your ability to provide insights about crops, yields, and production
                3. Asks how you can help them today
                Keep it under 50 words and make it conversational."""
            },
            'metric_selection': {
                'en': """Please select a metric you'd like to analyze for your agricultural data. 
                We can provide information about:
                - Area harvested
                - Yield
                - Production Quantity
                - Stocks
                What would you like to explore?"""
            },
            'crop_selection': {
                'en': f"""The farmer is interested in {context.get('metric', 'agricultural data')}.
                Create a natural prompt asking them to select a crop category and specific crop.
                Mention we have data for various categories like cereals, pulses, fruits, etc.
                Keep it conversational and brief."""
            },
            'data_view': {
                'en': f"""Here's the {context.get('metric', '')} data for {context.get('crop', '')}.
                I can show you trends, statistics, and insights about this data.
                What would you like to know more about?"""
            }
        }

        openai.api_key = constant.OPENAI_KEY
        base_prompt = system_prompts.get(stage, {}).get(language, system_prompts[stage]['en'])
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": base_prompt},
            ],
            temperature=0.7,
            max_tokens=100
        )
        
        prompt = response.choices[0].message.content
        self.cache_manager.set(cache_key, prompt)
        return prompt

class ChatbotUI:
    """Handle Streamlit UI components"""

    def __init__(
        self,
        data_manager: DataManager,
        prompt_manager: PromptManager,
        cache_manager: CacheManager
    ):
        self.data_manager = data_manager
        self.prompt_manager = prompt_manager
        self.cache_manager = cache_manager

    def show_welcome(self) -> None:
        st.markdown("### 🌾 Agricultural Data Assistant")
    
    # Debugging: Print session state before displaying prompt
        st.write("Session state (before welcome):", st.session_state)
        prompt = self.prompt_manager.get_prompt(
            'welcome',
            st.session_state.get('language', 'en'),
            {}
            )
        st.write(prompt)
        selected_lang = st.selectbox(
            "Select your preferred language",
            options=list(AgriculturalData.LANGUAGES.keys()),
            format_func=lambda x: f"{x} ({AgriculturalData.LANGUAGES[x]['local_name']})"
            )
        
        if st.button("Begin Exploration 🚀"):
            # Safeguard: explicitly set language and stage
            st.session_state.language = AgriculturalData.LANGUAGES[selected_lang]['code']
            st.session_state.stage = 'metric_selection'  # Explicitly set stage to 'metric_selection'
            st.session_state.context = {}  # Clear context to start fresh
            st.write("Session state (after setting):", st.session_state)  # Debugging
    
    # Remove rerun from this block


    def show_metric_selection(self) -> None:
        prompt = self.prompt_manager.get_prompt(
            'metric_selection',
            st.session_state.language,
            {}
        )
        st.write(prompt)

        metric = st.radio(
            "Select what you'd like to know:",
            options=list(AgriculturalData.METRICS.keys()),
            format_func=lambda x: (
                f"{x}: {AgriculturalData.METRICS[x]['description']} "
                f"({AgriculturalData.METRICS[x]['unit']})"
            )
        )

        if st.button("Continue"):
            st.session_state.context = {'metric': metric}
            st.session_state.stage = 'crop_selection'
            st.rerun()

    def show_crop_selection(self) -> None:
        st.write("Debug: Fetching available crops...")
        available_crops = self.data_manager.get_unique_items()
        st.write(f"Debug: Found {len(available_crops)} crops")
        
        if not available_crops:
            st.error("No crops found in the database. Please check the database connection and data structure.")
            if st.button("Retry"):
                st.rerun()
            return

        prompt = self.prompt_manager.get_prompt(
            'crop_selection',
            st.session_state.language,
            st.session_state.context
        )
        st.write(prompt)
        
        crop = st.selectbox(
            "Select crop",
            options=available_crops,
            key="crop_selector"
        )

        if st.button("View Data"):
            st.session_state.context.update({
                'crop': crop
            })
            st.session_state.stage = 'data_view'
            st.rerun()

    def show_data_view(self) -> None:
        context = st.session_state.context
        years = list(range(2015, 2024))
    
        st.write("Debug - Context:", context)
        
        try:
            with st.spinner(f"Fetching {context['crop']} data..."):
                df = self.data_manager.get_crop_data(
                    context['crop'],
                    context['metric'],
                    years
                )
        
                if df is not None and not df.empty:
                    st.markdown(f"### {context['crop']} - {context['metric']}")
                    
                    # Display summary statistics
                    stats = self.data_manager.get_data_summary(df)
                    col1, col2, col3 = st.columns(3)
                    for (stat, value), col in zip(stats.items(), [col1, col2, col3]):
                        col.metric(stat, value)
                    
                    # Display chart
                    chart_data = df.set_index('Year')['Value']
                    st.line_chart(chart_data)
                    
                    # Show raw data in expander
                    with st.expander("View Raw Data"):
                        st.dataframe(df)
                else:
                    st.error("No data available for the selected criteria")

        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.write("Debug - Full error:", str(e))
            st.info("Please verify that the selected crop and metric combination has available data.")

        if st.button("Start New Search"):
            st.session_state.stage = 'welcome'
            st.session_state.context = {}
            st.rerun()

def main():
    # Page config
    st.set_page_config(
        page_title="Agricultural Data Assistant",
        page_icon="🌾",
        layout="wide"
    )

    # Debugging: Print session state to ensure it's initialized
    st.write("Session state:", st.session_state)

    if 'stage' not in st.session_state:
        st.session_state.stage = 'welcome'  # Default to the 'welcome' stage
        st.session_state.context = {}
        st.session_state.language = 'en'  # Default to 'English'

    try:
        astra_client = AstraDB(
            token=constant.ASTRA_DB_TOKEN,
            api_endpoint=constant.ASTRA_DB_ENDPOINT
        )

        cache_manager = CacheManager(constant.REDIS_URL)
        data_manager = DataManager(astra_client, cache_manager)
        prompt_manager = PromptManager(openai, cache_manager)  # No explicit client needed

        chatbot_ui = ChatbotUI(data_manager, prompt_manager, cache_manager)

        if st.session_state.stage == 'welcome':
            chatbot_ui.show_welcome()
        elif st.session_state.stage == 'metric_selection':
            chatbot_ui.show_metric_selection()
        elif st.session_state.stage == 'crop_selection':
            chatbot_ui.show_crop_selection()
        elif st.session_state.stage == 'data_view':
            chatbot_ui.show_data_view()

    except Exception as e:
        st.error(f"Application Error: {str(e)}")
        if st.button("Restart Application"):
            st.session_state.stage = 'welcome'  # Go back to welcome screen
            st.session_state.context = {}  # Clear context
            st.rerun()  # Rerun the app



if __name__ == "__main__":
    main()