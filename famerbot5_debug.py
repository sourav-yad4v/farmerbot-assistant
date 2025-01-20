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
import farmerbot4, fetch_unique

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
        "Production": {
            "description": "Total quantity produced",
            "unit": "tonnes",
            "column": "Value"
        },
        "Producing Animals/Slaughtered": {
            "description": "Available inventory",
            "unit": "tonnes",
            "column": "Value"
        },
        "Stocks": {
           "description": "Current stock available",
           "unit": "tonnes",
            "column": "Value"
        },
        "Yield/Carcass Weight": {
            "description": "Weight of carcass produced per unit of animal",
            "unit": "kg",
            "column": "Value"
        },
        "Milk Animals": {
            "description": "Total number of milk-producing animals",
            "unit": "head",
            "column": "Value"
        },
        "Laying": {
            "description": "Total number of laying hens",
            "unit": "head",
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

    def get_crop_data(self, crop: str, metric: str, years: List[int]) -> pd.DataFrame:
        """Get crop data with caching"""
        try:
            # Try to fetch the data
            raw_result = fetch_unique.fetch_row_data(metric, crop, years[0])
            
            # Add detailed logging
            print(f"Raw result for {crop} - {metric}: {raw_result}")
            
            # Check if raw_result is None or empty
            if not raw_result:
                print(f"No data found in fetch_row_data for {crop} - {metric}")
                return pd.DataFrame()

            # Extract data from the metadata structure
            if isinstance(raw_result, dict) and 'metadata' in raw_result:
                # Single result case
                metadata = raw_result['metadata']
                formatted_data = [{
                    'Year': metadata.get('year', years[0]),
                    'Item': metadata.get('item', crop),
                    'Element': metadata.get('element', metric),
                    'Value': metadata.get('value', 0),
                    'Unit': metadata.get('unit', AgriculturalData.METRICS[metric]['unit']),
                    'Flag': metadata.get('flag', ''),
                    'Flag_Description': metadata.get('flag_description', '')
                }]
            elif isinstance(raw_result, list):
                # Multiple results case
                formatted_data = []
                for item in raw_result:
                    if isinstance(item, dict) and 'metadata' in item:
                        metadata = item['metadata']
                        formatted_data.append({
                            'Year': metadata.get('year', years[0]),
                            'Item': metadata.get('item', crop),
                            'Element': metadata.get('element', metric),
                            'Value': metadata.get('value', 0),
                            'Unit': metadata.get('unit', AgriculturalData.METRICS[metric]['unit']),
                            'Flag': metadata.get('flag', ''),
                            'Flag_Description': metadata.get('flag_description', '')
                        })
            else:
                print(f"Unexpected data format: {raw_result}")
                return pd.DataFrame()
            
            # Create DataFrame
            df = pd.DataFrame(formatted_data)
            
            if df.empty:
                print(f"No data found after formatting for {crop} - {metric}")
                return df
            
            # Ensure numeric type for Value column
            df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
            
            return df
            
        except Exception as e:
            print(f"Detailed error in get_crop_data: {str(e)}")
            return pd.DataFrame()

    def get_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate summary statistics for the data"""
        try:
            if df.empty or 'Value' not in df.columns:
                return {}
                
            summary = {
                'Value': f"{df['Value'].iloc[0]:,.2f}",
                'Status': df['Flag_Description'].iloc[0] if 'Flag_Description' in df.columns else 'N/A'
            }
            return summary
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
        prompt = self.prompt_manager.get_prompt(
            'crop_selection',
            st.session_state.language,
            st.session_state.context
        )
        st.write(prompt)

        metric = st.session_state.context.get('metric')
        if metric is None:
            st.error("No metric selected! Please go back and select a metric.")
            return

        # Fetch the unique crops for the selected metric using filter_items_by_element
        try:
            crops = farmerbot4.filter_items_by_element(metric)
            if not crops:
                st.error(f"No crops found for the selected metric: {metric}")
                return
        except Exception as e:
            st.error(f"Error fetching crops for metric {metric}: {str(e)}")
            return

        # Select specific crop
        crop = st.selectbox(
            "Select specific crop",
            options=crops
        )

        # Add Year selection dropdown with years from 1960 to 2023
        years = list(range(1960, 2024))  # Creating a list of years from 1960 to 2023
        selected_year = st.selectbox(
            "Select the year",
            options=years,
            index=63  # Default to the year 2023 (index 63 for 2023 in this range)
        )

        if st.button("View Data"):
            if not crop:
                st.error("Please select a crop.")
                return

            # Update context with crop and year
            st.session_state.context.update({
                'crop': crop,
                'year': selected_year  # Add year to the context
            })
            st.session_state.stage = 'data_view'
            st.rerun()

    def show_data_view(self) -> None:
        """Displays the data view for the selected crop and metric."""
        context = st.session_state.context
        selected_year = context.get('year', 2023)

        try:
            with st.spinner(f"Fetching {context['crop']} data..."):
                df = self.data_manager.get_crop_data(
                    context['crop'],
                    context['metric'],
                    [selected_year]
                )

            if df is not None and not df.empty:
                st.markdown(f"### {context['crop']} - {context['metric']} ({selected_year})")
                
                # Format the display value with the appropriate unit
                unit = df['Unit'].iloc[0] if 'Unit' in df.columns else AgriculturalData.METRICS[context['metric']]['unit']
                df['Display Value'] = df['Value'].apply(lambda x: f"{x:,.2f} {unit}")
                
                # Show formatted data
                display_df = df[['Year', 'Item', 'Element', 'Display Value']]
                if 'Flag_Description' in df.columns:
                    display_df['Status'] = df['Flag_Description']
                
                st.dataframe(display_df, use_container_width=True)
            
                # Display statistics
                stats = self.data_manager.get_data_summary(df)
                if stats:
                    col1, col2 = st.columns(2)
                    col1.metric(f"Value ({unit})", stats.get('Value', 'N/A'))
                    col2.metric("Status", stats.get('Status', 'N/A'))

            else:
                st.warning(
                    f"No data available for {context['crop']} - {context['metric']} in {selected_year}. "
                    "This combination might not exist in our database. Please try a different combination."
                )

        except Exception as e:
            st.error(f"Error fetching data: {str(e)}")
            st.info(
                "Please verify the selected crop and metric combination. "
                "Some crops might not have data for all metrics."
            )
    
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start New Search"):
                st.session_state.stage = 'welcome'
                st.session_state.context = {}
                st.rerun()
        with col2:
            if st.button("Try Different Metric"):
                st.session_state.stage = 'metric_selection'
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