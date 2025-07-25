#!/usr/bin/env python3
"""
Enhanced Workday Sub-page Scraper and Form Mapper

A robust web automation tool that:
1. Signs into Workday candidate accounts
2. Traverses multiple sub-pages in application flows
3. Extracts and maps all form controls to structured JSON
4. Handles dynamic elements, dropdowns, and various input types

Author: Web Automation Engineer
Usage: python workday_scraper.py --config config.json

IMPROVEMENTS MADE:
- Enhanced dynamic content detection
- Better multi-select handling
- Improved custom dropdown interaction
- More robust label detection
- Better error recovery
- Enhanced navigation logic
"""

import asyncio
import json
import logging
import argparse
import os
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, asdict
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright
import re
import time
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('workday_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class FormElement:
    """Data class representing a form element"""
    label: str
    id_of_input_component: str
    required: bool
    type_of_input: str
    options: Optional[List[str]] = None
    user_data_select_values: Optional[List[str]] = None

class WorkdayFormMapper:
    """Main class for mapping Workday forms"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.visited_urls: Set[str] = set()
        self.all_form_elements: List[FormElement] = []
        
        # Enhanced Workday-specific selectors
        self.form_selectors = {
            'text_inputs': [
                'input[type="text"]:visible',
                'input[type="email"]:visible', 
                'input[type="tel"]:visible',
                'input[type="number"]:visible',
                'input[type="url"]:visible',
                'input[type="password"]:visible',
                'input[data-automation-id*="textInputBox"]:visible',
                'input[data-automation-id*="textInput"]:visible',
                'input[data-automation-id*="numberInput"]:visible'
            ],
            'textareas': [
                'textarea:visible',
                '[data-automation-id*="textArea"]:visible',
                '[data-automation-id*="richTextEditor"]:visible'
            ],
            'selects': [
                'select:visible',
                '[data-automation-id*="dropdown"]:visible',
                '[data-automation-id*="searchDropDown"]:visible',
                '[data-automation-id*="selectWidget"]:visible',
                '[data-automation-id*="comboBox"]:visible',
                '[role="combobox"]:visible'
            ],
            'checkboxes': [
                'input[type="checkbox"]:visible',
                '[data-automation-id*="checkboxPanel"]:visible',
                '[data-automation-id*="checkbox"]:visible',
                '[role="checkbox"]:visible'
            ],
            'radios': [
                'input[type="radio"]:visible',
                '[data-automation-id*="radioButton"]:visible',
                '[data-automation-id*="radio"]:visible',
                '[role="radio"]:visible'
            ],
            'date_inputs': [
                'input[type="date"]:visible',
                '[data-automation-id*="datePicker"]:visible',
                '[data-automation-id*="dateInput"]:visible',
                '[data-automation-id*="dateWidget"]:visible'
            ],
            'file_inputs': [
                'input[type="file"]:visible',
                '[data-automation-id*="fileUpload"]:visible',
                '[data-automation-id*="attachmentWidget"]:visible'
            ]
        }

    async def initialize_browser(self):
        """Initialize Playwright browser with optimal settings"""
        logger.info("Initializing browser...")
        
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.config.get('headless', True),
            slow_mo=self.config.get('slow_mo', 100),
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--allow-running-insecure-content',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9'
            }
        )
        
        # Set up page with better error handling
        self.page = await self.context.new_page()
        
        # Set longer timeouts
        self.page.set_default_timeout(60000)
        self.page.set_default_navigation_timeout(60000)

    async def find_workday_login_url(self, start_url: str) -> str:
        """Find the actual login URL from various Workday page types"""
        try:
            logger.info(f"Analyzing URL: {start_url}")
            await self.page.goto(start_url, wait_until='domcontentloaded', timeout=60000)
            await self.page.wait_for_timeout(3000)  # Wait for any redirects
            
            current_url = self.page.url.lower()
            
            # If already on login page, return it
            if any(keyword in current_url for keyword in ['signin', 'login', 'candidate']):
                logger.info("Already on login/candidate page")
                return self.page.url
            
            # Look for various login/apply entry points
            entry_selectors = [
                # Direct sign-in links
                'a[data-automation-id*="signIn"]',
                'button[data-automation-id*="signIn"]',
                'a[href*="signin"]',
                'a[href*="login"]',
                'a[href*="candidate"]',
                
                # Apply buttons that lead to login
                'a[data-automation-id*="apply"]',
                'button[data-automation-id*="apply"]',
                
                # Text-based selectors
                'a:has-text("Sign In")',
                'button:has-text("Sign In")',
                'a:has-text("Apply Now")',
                'button:has-text("Apply Now")',
                'a:has-text("Apply")',
                'button:has-text("Apply")',
                
                # Career site navigation
                'a[href*="careers"]',
                'a[href*="jobs"]'
            ]
            
            for selector in entry_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for element in elements:
                        if await element.is_visible():
                            href = await element.get_attribute('href')
                            text = await element.inner_text()
                            logger.info(f"Found potential entry point: {text} -> {href}")
                            
                            # Click and see where it takes us
                            await element.click()
                            await self.page.wait_for_load_state('domcontentloaded')
                            await self.page.wait_for_timeout(2000)
                            
                            new_url = self.page.url
                            if new_url != start_url:
                                logger.info(f"Redirected to: {new_url}")
                                return new_url
                            
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
                    continue
            
            # If no specific entry point found, try to extract base career site URL
            parsed = urlparse(start_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Common Workday career site patterns
            potential_urls = [
                f"{base_url}/candidate",
                f"{base_url}/signin",
                f"{base_url}/login",
                start_url.replace('/details/', '/').split('?')[0]  # Remove job details
            ]
            
            for url in potential_urls:
                try:
                    logger.info(f"Trying potential URL: {url}")
                    await self.page.goto(url, wait_until='domcontentloaded')
                    await self.page.wait_for_timeout(2000)
                    
                    # Check if this looks like a login or career portal page
                    if await self.page.query_selector('input[type="email"], input[type="password"], input[data-automation-id*="email"]'):
                        logger.info(f"Found login form at: {url}")
                        return url
                        
                except Exception as e:
                    logger.debug(f"Failed to access {url}: {e}")
                    continue
            
            # Return original URL as fallback
            logger.warning("Could not find specific login URL, using original")
            return start_url
            
        except Exception as e:
            logger.error(f"Error finding login URL: {e}")
            return start_url

    async def login(self) -> bool:
        """Login to Workday with provided credentials"""
        try:
            # First, find the correct login URL
            login_url = await self.find_workday_login_url(self.config['workday_url'])
            
            logger.info(f"Attempting login at: {login_url}")
            await self.page.goto(login_url, wait_until='domcontentloaded', timeout=60000)
            await self.page.wait_for_timeout(3000)
            
            # Multiple strategies to find login form
            login_attempts = [
                # Strategy 1: Standard Workday selectors
                {
                    'email': 'input[data-automation-id="email"]',
                    'password': 'input[data-automation-id="password"]',
                    'submit': 'button[data-automation-id="signInSubmitButton"]'
                },
                # Strategy 2: Alternative automation IDs
                {
                    'email': 'input[data-automation-id="emailAddress"]',
                    'password': 'input[data-automation-id="password"]',
                    'submit': 'button[data-automation-id="submitButton"]'
                },
                # Strategy 3: Standard HTML form elements
                {
                    'email': 'input[type="email"]',
                    'password': 'input[type="password"]',
                    'submit': 'button[type="submit"]'
                },
                # Strategy 4: Name-based selectors
                {
                    'email': 'input[name="username"], input[name="email"]',
                    'password': 'input[name="password"]',
                    'submit': 'input[type="submit"], button:has-text("Sign In"), button:has-text("Log In")'
                }
            ]
            
            login_success = False
            
            for i, attempt in enumerate(login_attempts):
                try:
                    logger.info(f"Trying login strategy {i+1}...")
                    
                    # Wait for and find email field
                    email_field = await self.page.wait_for_selector(attempt['email'], timeout=10000)
                    if not email_field or not await email_field.is_visible():
                        logger.debug(f"Email field not found or visible with selector: {attempt['email']}")
                        continue
                    
                    # Find password field
                    password_field = await self.page.query_selector(attempt['password'])
                    if not password_field or not await password_field.is_visible():
                        logger.debug(f"Password field not found or visible with selector: {attempt['password']}")
                        continue
                    
                    # Find submit button
                    submit_button = await self.page.query_selector(attempt['submit'])
                    if not submit_button:
                        logger.debug(f"Submit button not found with selector: {attempt['submit']}")
                        continue
                    
                    # Fill credentials
                    logger.info("Filling login credentials...")
                    await email_field.clear()
                    await email_field.fill(self.config['username'])
                    
                    await password_field.clear()
                    await password_field.fill(self.config['password'])
                    
                    # Submit form
                    logger.info("Submitting login form...")
                    await submit_button.click()
                    
                    # Wait for navigation or error
                    try:
                        await self.page.wait_for_load_state('networkidle', timeout=30000)
                    except:
                        await self.page.wait_for_timeout(5000)  # Fallback wait
                    
                    # Check if login was successful
                    current_url = self.page.url.lower()
                    
                    # Look for indicators of successful login
                    success_indicators = [
                        # URL doesn't contain login/signin
                        not any(keyword in current_url for keyword in ['login', 'signin', 'sign-in']),
                        # Or look for dashboard/profile elements
                        await self.page.query_selector('[data-automation-id*="dashboard"], [data-automation-id*="profile"], .wd-navigation'),
                        # Or absence of login form
                        not await self.page.query_selector('input[type="password"]:visible')
                    ]
                    
                    if any(success_indicators):
                        logger.info("Login successful!")
                        login_success = True
                        break
                    else:
                        # Check for error messages
                        error_selectors = [
                            '[data-automation-id*="error"]',
                            '.wd-error',
                            '[role="alert"]',
                            '.error-message'
                        ]
                        
                        for error_sel in error_selectors:
                            error_elem = await self.page.query_selector(error_sel)
                            if error_elem and await error_elem.is_visible():
                                error_text = await error_elem.inner_text()
                                logger.error(f"Login error: {error_text}")
                                break
                        
                        logger.warning(f"Login attempt {i+1} failed, trying next strategy...")
                        continue
                
                except Exception as e:
                    logger.debug(f"Login strategy {i+1} failed with error: {e}")
                    continue
            
            if not login_success:
                logger.error("All login strategies failed")
                
                # Debug: Log available form elements
                logger.info("Available form elements on page:")
                inputs = await self.page.query_selector_all('input')
                for inp in inputs[:10]:  # Limit to first 10
                    try:
                        input_type = await inp.get_attribute('type') or 'text'
                        automation_id = await inp.get_attribute('data-automation-id') or 'none'
                        name = await inp.get_attribute('name') or 'none'
                        placeholder = await inp.get_attribute('placeholder') or 'none'
                        visible = await inp.is_visible()
                        logger.info(f"  Input: type={input_type}, automation-id={automation_id}, name={name}, placeholder={placeholder}, visible={visible}")
                    except:
                        continue
                
                return False
                
            return True
                
        except Exception as e:
            logger.error(f"Login failed with exception: {str(e)}")
            logger.debug(traceback.format_exc())
            return False

    async def find_navigation_links(self) -> List[str]:
        """Find all internal navigation links on current page"""
        try:
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_timeout(2000)
            
            # Enhanced Workday navigation patterns
            nav_selectors = [
                'a[href*="/candidate/"]:visible',
                'a[data-automation-id*="navigationLink"]:visible',
                'a[data-automation-id*="stepNavigationButton"]:visible',
                'button[data-automation-id*="navigationButton"]:visible',
                '.wd-navigation a:visible',
                '[role="navigation"] a:visible',
                'a[href*="/application/"]:visible',
                'a[data-automation-id*="continueButton"]:visible',
                'button[data-automation-id*="continueButton"]:visible',
                'a[data-automation-id*="nextButton"]:visible',
                'button[data-automation-id*="nextButton"]:visible',
                'a[data-automation-id*="menuItem"]:visible',
                'a[data-automation-id*="tabPanel"]:visible',
                '[role="tab"] a:visible',
                '.wd-step-navigation a:visible'
            ]
            
            links = []
            base_domain = urlparse(self.config['workday_url']).netloc
            current_path = urlparse(self.page.url).path
            
            for selector in nav_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for element in elements:
                        try:
                            if not await element.is_visible():
                                continue
                                
                            href = await element.get_attribute('href')
                            if not href:
                                continue
                            
                            # Make absolute URL
                            if href.startswith('/'):
                                full_url = f"https://{base_domain}{href}"
                            elif href.startswith('http'):
                                full_url = href
                            else:
                                full_url = urljoin(self.page.url, href)
                            
                            parsed = urlparse(full_url)
                            
                            # Only include internal links from same domain
                            if (parsed.netloc == base_domain and 
                                full_url not in self.visited_urls and
                                full_url not in links and
                                parsed.path != current_path and
                                not any(skip in full_url.lower() for skip in ['logout', 'signout', 'exit', 'cancel'])):
                                
                                # Get link text for context
                                link_text = await element.inner_text()
                                logger.info(f"Found navigation link: {link_text} -> {full_url}")
                                links.append(full_url)
                                
                        except Exception as e:
                            logger.debug(f"Error processing navigation element: {e}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
                    continue
            
            logger.info(f"Found {len(links)} navigation links on current page")
            return links
            
        except Exception as e:
            logger.error(f"Error finding navigation links: {e}")
            return []

    async def extract_form_elements(self) -> List[FormElement]:
        """Extract all form elements from current page"""
        logger.info(f"Extracting form elements from: {self.page.url}")
        elements = []
        
        try:
            # Wait for dynamic content to load
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_timeout(3000)
            
            # Wait for any dynamic forms to appear
            try:
                await self.page.wait_for_selector('form, input, select, textarea', timeout=5000)
            except:
                pass  # No forms on page
            
            # Extract different types of form elements
            elements.extend(await self._extract_text_inputs())
            elements.extend(await self._extract_textareas())
            elements.extend(await self._extract_selects())
            elements.extend(await self._extract_checkboxes())
            elements.extend(await self._extract_radios())
            elements.extend(await self._extract_date_inputs())
            elements.extend(await self._extract_file_inputs())
            
            # Remove duplicates based on id
            unique_elements = []
            seen_ids = set()
            
            for element in elements:
                if element.id_of_input_component not in seen_ids:
                    unique_elements.append(element)
                    seen_ids.add(element.id_of_input_component)
            
            logger.info(f"Extracted {len(unique_elements)} unique form elements from current page")
            return unique_elements
            
        except Exception as e:
            logger.error(f"Error extracting form elements: {e}")
            logger.debug(traceback.format_exc())
            return []

    async def _extract_text_inputs(self) -> List[FormElement]:
        """Extract text input elements"""
        elements = []
        
        for selector in self.form_selectors['text_inputs']:
            try:
                inputs = await self.page.query_selector_all(selector)
                
                for input_elem in inputs:
                    try:
                        if not await input_elem.is_visible() or await input_elem.is_disabled():
                            continue
                            
                        element_data = await self._get_element_data(input_elem, 'text')
                        if element_data and element_data.id_of_input_component:
                            # Determine sample value based on input type and label
                            sample_value = await self._generate_sample_text_value(element_data.label, input_elem)
                            element_data.user_data_select_values = [sample_value]
                            elements.append(element_data)
                            
                    except Exception as e:
                        logger.debug(f"Error processing text input: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Error with text input selector {selector}: {e}")
                continue
                    
        return elements

    async def _generate_sample_text_value(self, label: str, element) -> str:
        """Generate appropriate sample values based on field type"""
        label_lower = label.lower()
        input_type = await element.get_attribute('type') or 'text'
        
        # Email fields
        if 'email' in label_lower or input_type == 'email':
            return 'test@example.com'
        
        # Phone fields
        if any(word in label_lower for word in ['phone', 'mobile', 'tel']):
            return '+1-555-123-4567'
        
        # Name fields
        if 'first name' in label_lower or 'given name' in label_lower:
            return 'John'
        elif 'last name' in label_lower or 'family name' in label_lower or 'surname' in label_lower:
            return 'Doe'
        elif any(word in label_lower for word in ['name', 'applicant']):
            return 'John Doe'
        
        # Address fields
        if 'address' in label_lower:
            if 'line 2' in label_lower or 'apt' in label_lower:
                return 'Apt 123'
            return '123 Main Street'
        elif 'city' in label_lower:
            return 'New York'
        elif any(word in label_lower for word in ['state', 'province']):
            return 'NY'
        elif any(word in label_lower for word in ['zip', 'postal']):
            return '10001'
        
        # Numeric fields
        if input_type == 'number' or any(word in label_lower for word in ['years', 'salary', 'gpa']):
            return '5'
        
        # URL fields
        if input_type == 'url' or 'website' in label_lower or 'url' in label_lower:
            return 'https://example.com'
        
        # Default
        return 'Sample Text'

    async def _extract_textareas(self) -> List[FormElement]:
        """Extract textarea elements"""
        elements = []
        
        for selector in self.form_selectors['textareas']:
            try:
                textareas = await self.page.query_selector_all(selector)
                
                for textarea in textareas:
                    try:
                        if not await textarea.is_visible() or await textarea.is_disabled():
                            continue
                            
                        element_data = await self._get_element_data(textarea, 'textarea')
                        if element_data and element_data.id_of_input_component:
                            element_data.user_data_select_values = ['This is sample text area content for testing purposes.']
                            elements.append(element_data)
                            
                    except Exception as e:
                        logger.debug(f"Error processing textarea: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Error with textarea selector {selector}: {e}")
                continue
                    
        return elements

    async def _extract_selects(self) -> List[FormElement]:
        """Extract select/dropdown elements with enhanced custom dropdown handling"""
        elements = []
        
        for selector in self.form_selectors['selects']:
            try:
                selects = await self.page.query_selector_all(selector)
                
                for select in selects:
                    try:
                        if not await select.is_visible() or await select.is_disabled():
                            continue
                        
                        # Check if it's a multi-select
                        tag_name = await select.evaluate('el => el.tagName.toLowerCase()')
                        is_multiple = await select.get_attribute('multiple') is not None
                        
                        # Check for Workday multi-select indicators
                        automation_id = await select.get_attribute('data-automation-id') or ''
                        if 'multi' in automation_id.lower():
                            is_multiple = True
                        
                        input_type = 'multiselect' if is_multiple else 'select'
                        
                        element_data = await self._get_element_data(select, input_type)
                        if element_data and element_data.id_of_input_component:
                            
                            # Extract options with enhanced methods
                            options = await self._get_select_options(select)
                            element_data.options = options
                            
                            # Generate sample values
                            if options:
                                sample_count = min(2 if is_multiple else 1, len(options))
                                element_data.user_data_select_values = options[:sample_count]
                            
                            elements.append(element_data)
                            
                    except Exception as e:
                        logger.debug(f"Error processing select: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Error with select selector {selector}: {e}")
                continue
                    
        return elements

    async def _extract_checkboxes(self) -> List[FormElement]:
        """Extract checkbox elements with better grouping"""
        elements = []
        processed_groups = set()
        
        for selector in self.form_selectors['checkboxes']:
            try:
                checkboxes = await self.page.query_selector_all(selector)
                
                for checkbox in checkboxes:
                    try:
                        if not await checkbox.is_visible() or await checkbox.is_disabled():
                            continue
                        
                        # Check if this is part of a checkbox group
                        name = await checkbox.get_attribute('name')
                        group_key = name if name else await checkbox.get_attribute('data-automation-id')
                        
                        if group_key and group_key in processed_groups:
                            continue
                        
                        element_data = await self._get_element_data(checkbox, 'checkbox')
                        if element_data and element_data.id_of_input_component:
                            
                            # For checkbox groups, collect all options
                            if name:
                                group_checkboxes = await self.page.query_selector_all(f'input[name="{name}"]')
                                if len(group_checkboxes) > 1:
                                    # This is a checkbox group
                                    options = []
                                    for cb in group_checkboxes:
                                        try:
                                            if await cb.is_visible():
                                                cb_label = await self._find_element_label(cb)
                                                if cb_label and cb_label not in options:
                                                    options.append(cb_label)
                                        except:
                                            continue
                                    
                                    if options:
                                        element_data.options = options
                                        element_data.user_data_select_values = [options[0]]  # Select first option
                                        processed_groups.add(group_key)
                                        elements.append(element_data)
                                        continue
                            
                            # Single checkbox
                            label_text = element_data.label.lower()
                            if any(word in label_text for word in ['yes', 'no', 'agree', 'consent', 'accept']):
                                element_data.options = ['Yes', 'No']
                                element_data.user_data_select_values = ['Yes']
                            else:
                                element_data.options = ['Checked', 'Unchecked']
                                element_data.user_data_select_values = ['Checked']
                            
                            elements.append(element_data)
                            
                    except Exception as e:
                        logger.debug(f"Error processing checkbox: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Error with checkbox selector {selector}: {e}")
                continue
                    
        return elements

    async def _extract_radios(self) -> List[FormElement]:
        """Extract radio button elements"""
        elements = []
        processed_groups = set()
        
        for selector in self.form_selectors['radios']:
            try:
                radios = await self.page.query_selector_all(selector)
                
                for radio in radios:
                    try:
                        if not await radio.is_visible() or await radio.is_disabled():
                            continue
                        
                        # Group radio buttons by name attribute
                        name = await radio.get_attribute('name')
                        if not name or name in processed_groups:
                            continue
                            
                        processed_groups.add(name)
                        
                        # Get all radios in this group
                        group_radios = await self.page.query_selector_all(f'input[name="{name}"]')
                        options = []
                        
                        for r in group_radios:
                            try:
                                if await r.is_visible():
                                    value = await r.get_attribute('value')
                                    if value and value not in options:
                                        options.append(value)
                                    else:
                                        # Try to get label text
                                        label = await self._find_element_label(r)
                                        if label and label not in options:
                                            options.append(label)
                            except:
                                continue
                        
                        element_data = await self._get_element_data(radio, 'radio')
                        if element_data and element_data.id_of_input_component:
                            element_data.options = options if options else ['Option 1', 'Option 2']
                            if element_data.options:
                                element_data.user_data_select_values = [element_data.options[0]]
                            
                            elements.append(element_data)
                            
                    except Exception as e:
                        logger.debug(f"Error processing radio: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Error with radio selector {selector}: {e}")
                continue
                    
        return elements

    async def _extract_date_inputs(self) -> List[FormElement]:
        """Extract date input elements"""
        elements = []
        
        for selector in self.form_selectors['date_inputs']:
            try:
                dates = await self.page.query_selector_all(selector)
                
                for date_input in dates:
                    try:
                        if not await date_input.is_visible() or await date_input.is_disabled():
                            continue
                            
                        element_data = await self._get_element_data(date_input, 'date')
                        if element_data and element_data.id_of_input_component:
                            # Generate appropriate sample date based on field context
                            sample_date = await self._generate_sample_date(element_data.label)
                            element_data.user_data_select_values = [sample_date]
                            elements.append(element_data)
                            
                    except Exception as e:
                        logger.debug(f"Error processing date input: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Error with date selector {selector}: {e}")
                continue
                    
        return elements

    async def _generate_sample_date(self, label: str) -> str:
        """Generate appropriate sample dates based on field context"""
        label_lower = label.lower()
        
        # Birth date
        if any(word in label_lower for word in ['birth', 'born', 'dob']):
            return '1990-01-15'
        
        # Start dates (work, education)
        if any(word in label_lower for word in ['start', 'begin', 'from']):
            return '2020-01-01'
        
        # End dates
        if any(word in label_lower for word in ['end', 'until', 'to', 'finish']):
            return '2023-12-31'
        
        # Graduation
        if any(word in label_lower for word in ['graduation', 'graduate', 'degree']):
            return '2022-05-15'
        
        # Available/preferred start date
        if any(word in label_lower for word in ['available', 'prefer', 'earliest']):
            return '2024-02-01'
        
        # Default - recent past date
        return '2023-06-15'

    async def _extract_file_inputs(self) -> List[FormElement]:
        """Extract file input elements"""
        elements = []
        
        for selector in self.form_selectors['file_inputs']:
            try:
                files = await self.page.query_selector_all(selector)
                
                for file_input in files:
                    try:
                        if not await file_input.is_visible() or await file_input.is_disabled():
                            continue
                            
                        element_data = await self._get_element_data(file_input, 'file')
                        if element_data and element_data.id_of_input_component:
                            # Determine accepted file types
                            accept_attr = await file_input.get_attribute('accept')
                            if accept_attr:
                                element_data.options = accept_attr.split(',')
                            else:
                                element_data.options = ['.pdf', '.doc', '.docx']
                            
                            element_data.user_data_select_values = ['resume.pdf']
                            elements.append(element_data)
                            
                    except Exception as e:
                        logger.debug(f"Error processing file input: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Error with file selector {selector}: {e}")
                continue
                    
        return elements

    async def _get_element_data(self, element, input_type: str) -> Optional[FormElement]:
        """Extract common data from any form element"""
        try:
            # Get identifier (prefer data-automation-id, fallback to id, then name)
            element_id = (
                await element.get_attribute('data-automation-id') or
                await element.get_attribute('id') or
                await element.get_attribute('name') or
                f"element_{abs(hash(str(element)))}"
            )
            
            # Get label
            label = await self._find_element_label(element)
            
            # Check if required
            required = await self._is_element_required(element)
            
            return FormElement(
                label=label,
                id_of_input_component=element_id,
                required=required,
                type_of_input=input_type
            )
            
        except Exception as e:
            logger.debug(f"Error getting element data: {e}")
            return None

    async def _find_element_label(self, element) -> str:
        """Find label text for an element using multiple strategies"""
        try:
            # Strategy 1: aria-label
            aria_label = await element.get_attribute('aria-label')
            if aria_label and len(aria_label.strip()) > 0:
                return aria_label.strip()
            
            # Strategy 2: aria-labelledby
            labelledby = await element.get_attribute('aria-labelledby')
            if labelledby:
                try:
                    label_elem = await self.page.query_selector(f'#{labelledby}')
                    if label_elem:
                        label_text = await label_elem.inner_text()
                        if label_text and len(label_text.strip()) > 0:
                            return label_text.strip()
                except:
                    pass
            
            # Strategy 3: associated label element
            element_id = await element.get_attribute('id')
            if element_id:
                label_elem = await self.page.query_selector(f'label[for="{element_id}"]')
                if label_elem:
                    label_text = await label_elem.inner_text()
                    if label_text and len(label_text.strip()) > 0:
                        return label_text.strip()
            
            # Strategy 4: Workday-specific label patterns
            workday_label_selectors = [
                # Direct sibling or parent labels
                'xpath=./preceding-sibling::label[1]',
                'xpath=./following-sibling::label[1]',
                'xpath=../label',
                'xpath=../../label',
                
                # Workday specific patterns
                'xpath=./preceding-sibling::*[contains(@class, "wd-label")][1]',
                'xpath=..//*[contains(@data-automation-id, "label")]',
                'xpath=./preceding-sibling::*[contains(@data-automation-id, "fieldLabel")][1]'
            ]
            
            for selector in workday_label_selectors:
                try:
                    label_elem = await element.query_selector(selector)
                    if label_elem and await label_elem.is_visible():
                        label_text = await label_elem.inner_text()
                        if label_text and 5 < len(label_text.strip()) < 200:
                            return label_text.strip()
                except:
                    continue
            
            # Strategy 5: parent/ancestor with label-like content
            current = element
            for level in range(4):  # Check up to 4 levels up
                try:
                    parent = await current.query_selector('xpath=..')
                    if not parent:
                        break
                        
                    # Look for label elements in parent
                    labels = await parent.query_selector_all('label, .wd-label, [data-automation-id*="label"], .fieldLabel, .wd-input-label')
                    for label in labels:
                        if await label.is_visible():
                            label_text = await label.inner_text()
                            if label_text and 5 < len(label_text.strip()) < 200:
                                return label_text.strip()
                    
                    current = parent
                except:
                    break
            
            # Strategy 6: placeholder text
            placeholder = await element.get_attribute('placeholder')
            if placeholder and len(placeholder.strip()) > 0:
                return f"Field: {placeholder.strip()}"
            
            # Strategy 7: nearby text content with better filtering
            try:
                parent = await element.query_selector('xpath=..')
                if parent:
                    parent_text = await parent.inner_text()
                    if parent_text:
                        # Clean and filter text
                        lines = parent_text.split('\n')
                        for line in lines:
                            clean_line = re.sub(r'\s+', ' ', line).strip()
                            # Look for question-like patterns
                            if (5 < len(clean_line) < 150 and 
                                (clean_line.endswith('?') or 
                                 clean_line.endswith(':') or
                                 any(word in clean_line.lower() for word in ['enter', 'select', 'choose', 'provide']))):
                                return clean_line
            except:
                pass
            
            # Strategy 8: Use element attributes for context
            element_type = await element.get_attribute('type')
            element_name = await element.get_attribute('name')
            automation_id = await element.get_attribute('data-automation-id')
            
            # Use automation ID if meaningful
            if automation_id and len(automation_id) > 5:
                # Convert automation ID to readable text
                readable_name = re.sub(r'[_-]', ' ', automation_id)
                readable_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', readable_name)
                return readable_name.title()
            
            if element_name:
                # Convert camelCase/snake_case to readable text
                readable_name = re.sub(r'[_-]', ' ', element_name)
                readable_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', readable_name)
                return readable_name.title()
            
            # Fallback
            return f"Unnamed {element_type or input_type} field"
            
        except Exception as e:
            logger.debug(f"Error finding element label: {e}")
            return f"Unknown {input_type} field"

    async def _is_element_required(self, element) -> bool:
        """Check if element is required using multiple strategies"""
        try:
            # Strategy 1: HTML required attribute
            if await element.get_attribute('required') is not None:
                return True
            
            # Strategy 2: ARIA required
            if await element.get_attribute('aria-required') == 'true':
                return True
            
            # Strategy 3: Workday-specific required indicators
            try:
                # Check element itself for required classes
                class_name = await element.get_attribute('class') or ''
                if 'required' in class_name.lower():
                    return True
                
                # Check parent elements for required indicators
                parent = await element.query_selector('xpath=..')
                if parent:
                    required_indicators = await parent.query_selector_all(
                        '.wd-required, [data-automation-id*="required"], .required, .mandatory, .wd-validation-required'
                    )
                    if required_indicators:
                        return True
                    
                    # Check for asterisk or "required" text in parent
                    parent_html = await parent.inner_html()
                    if parent_html and ('*' in parent_html or 'required' in parent_html.lower()):
                        return True
                        
                    # Check parent's class names
                    parent_class = await parent.get_attribute('class') or ''
                    if 'required' in parent_class.lower():
                        return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking if element is required: {e}")
            return False

    async def _get_select_options(self, select_element) -> List[str]:
        """Extract options from select element with enhanced custom dropdown handling"""
        try:
            options = []
            
            # Strategy 1: Standard HTML select options
            option_elements = await select_element.query_selector_all('option')
            
            if option_elements:
                for option in option_elements:
                    try:
                        text = await option.inner_text()
                        value = await option.get_attribute('value')
                        
                        # Prefer text over value, skip empty/placeholder options
                        option_text = text.strip() if text else (value or '').strip()
                        if (option_text and 
                            option_text.lower() not in ['', 'select...', 'choose...', 'please select', '-- select --', 'select an option']):
                            options.append(option_text)
                    except:
                        continue
            else:
                # Strategy 2: Enhanced Workday custom dropdowns
                try:
                    # Scroll element into view
                    await select_element.scroll_into_view_if_needed()
                    await self.page.wait_for_timeout(500)
                    
                    # Try to activate dropdown to reveal options
                    await select_element.click()
                    await self.page.wait_for_timeout(1500)  # Wait for dropdown to appear
                    
                    # Look for dropdown options in various Workday formats
                    option_selectors = [
                        '[data-automation-id*="dropdown"] li:visible',
                        '[role="option"]:visible',
                        '.wd-popup-content li:visible',
                        '[data-automation-id*="listbox"] div:visible',
                        '.wd-dropdown-list li:visible',
                        '[data-automation-id*="menuItem"]:visible',
                        '.wd-popup [role="menuitem"]:visible',
                        '[data-automation-id*="option"]:visible',
                        '.wd-list-item:visible'
                    ]
                    
                    for selector in option_selectors:
                        try:
                            # Wait briefly for options to appear
                            await self.page.wait_for_timeout(500)
                            option_elements = await self.page.query_selector_all(selector)
                            
                            if option_elements:
                                for option in option_elements[:20]:  # Limit to prevent too many options
                                    try:
                                        if await option.is_visible():
                                            text = await option.inner_text()
                                            if (text and text.strip() and 
                                                len(text.strip()) < 100 and
                                                text.strip() not in options and
                                                text.strip().lower() not in ['select...', 'choose...', 'loading...']):
                                                options.append(text.strip())
                                    except:
                                        continue
                                
                                if options:
                                    break
                        except:
                            continue
                    
                    # Try typing to reveal typeahead options
                    if not options:
                        try:
                            # Clear any existing text and type 'a' to trigger typeahead
                            await select_element.clear()
                            await select_element.type('a', delay=100)
                            await self.page.wait_for_timeout(1000)
                            
                            # Look for typeahead suggestions
                            suggestion_selectors = [
                                '[role="option"]:visible',
                                '.wd-suggestion:visible',
                                '[data-automation-id*="typeahead"] li:visible'
                            ]
                            
                            for selector in suggestion_selectors:
                                suggestion_elements = await self.page.query_selector_all(selector)
                                for suggestion in suggestion_elements[:10]:
                                    if await suggestion.is_visible():
                                        text = await suggestion.inner_text()
                                        if text and text.strip() and len(text.strip()) < 100:
                                            options.append(text.strip())
                                if options:
                                    break
                                    
                            # Clear the field after testing
                            await select_element.clear()
                            
                        except:
                            pass
                    
                    # Close dropdown by pressing Escape or clicking elsewhere
                    try:
                        await self.page.keyboard.press('Escape')
                        await self.page.wait_for_timeout(500)
                    except:
                        try:
                            # Click somewhere else to close dropdown
                            await self.page.click('body')
                            await self.page.wait_for_timeout(500)
                        except:
                            pass
                    
                except Exception as e:
                    logger.debug(f"Error interacting with custom dropdown: {e}")
            
            # Remove duplicates while preserving order
            unique_options = []
            seen = set()
            for option in options:
                if option and option not in seen:
                    unique_options.append(option)
                    seen.add(option)
            
            return unique_options[:15]  # Limit to first 15 options
            
        except Exception as e:
            logger.debug(f"Error getting select options: {e}")
            return []

    async def crawl_and_extract(self) -> List[FormElement]:
        """Main crawling method - traverse pages and extract form elements"""
        try:
            if not await self.login():
                logger.error("Failed to login, aborting crawl")
                return []
            
            # Start with current page after login
            pages_to_visit = [self.page.url]
            pages_processed = 0
            max_pages = self.config.get('max_pages', 10)
            
            logger.info(f"Starting crawl with max {max_pages} pages")
            
            while pages_to_visit and pages_processed < max_pages:
                current_url = pages_to_visit.pop(0)
                
                if current_url in self.visited_urls:
                    continue
                
                logger.info(f"Processing page {pages_processed + 1}/{max_pages}: {current_url}")
                
                try:
                    # Navigate to page if not already there
                    if self.page.url != current_url:
                        await self.page.goto(current_url, wait_until='domcontentloaded', timeout=45000)
                        await self.page.wait_for_timeout(3000)
                    
                    self.visited_urls.add(current_url)
                    
                    # Extract form elements from current page
                    page_elements = await self.extract_form_elements()
                    
                    if page_elements:
                        logger.info(f"Found {len(page_elements)} form elements on this page")
                        self.all_form_elements.extend(page_elements)
                    else:
                        logger.info("No form elements found on this page")
                    
                    # Find new navigation links
                    new_links = await self.find_navigation_links()
                    
                    # Add new links to visit queue (limit to prevent infinite crawling)
                    for link in new_links[:5]:  # Limit to 5 new links per page
                        if link not in self.visited_urls and link not in pages_to_visit:
                            pages_to_visit.append(link)
                    
                    pages_processed += 1
                    
                    # Add delay between pages to be respectful
                    if pages_processed < max_pages:
                        await self.page.wait_for_timeout(self.config.get('wait_between_pages', 2000))
                    
                except Exception as e:
                    logger.error(f"Error processing page {current_url}: {e}")
                    logger.debug(traceback.format_exc())
                    continue
            
            # Remove duplicates from final results
            unique_elements = []
            seen_ids = set()
            
            for element in self.all_form_elements:
                if element.id_of_input_component not in seen_ids:
                    unique_elements.append(element)
                    seen_ids.add(element.id_of_input_component)
            
            logger.info(f"Crawl completed! Processed {pages_processed} pages, found {len(unique_elements)} unique form elements")
            return unique_elements
            
        except Exception as e:
            logger.error(f"Error during crawl: {e}")
            logger.debug(traceback.format_exc())
            return []

    async def cleanup(self):
        """Clean up browser resources properly"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error during cleanup: {e}")

    def export_results(self, filename: str = 'workday_form_elements.json'):
        """Export results to JSON file"""
        try:
            # Convert to dictionaries for JSON serialization
            results = [asdict(element) for element in self.all_form_elements]
            
            # Add metadata
            metadata = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_elements': len(results),
                'pages_visited': len(self.visited_urls),
                'workday_url': self.config['workday_url'],
                'visited_urls': list(self.visited_urls)
            }
            
            output = {
                'metadata': metadata,
                'form_elements': results
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results exported to {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error exporting results: {e}")
            return None

async def main():
    """Main function with improved error handling"""
    parser = argparse.ArgumentParser(description='Workday Form Scraper')
    parser.add_argument('--config', required=True, help='Path to configuration JSON file')
    parser.add_argument('--output', default='workday_form_elements.json', help='Output JSON file')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        return
    
    # Override headless setting if specified
    if args.headless:
        config['headless'] = True
    
    # Override with environment variables if available (more secure)
    config['workday_url'] = os.getenv('WORKDAY_URL', config.get('workday_url'))
    config['username'] = os.getenv('WORKDAY_USERNAME', config.get('username'))
    config['password'] = os.getenv('WORKDAY_PASSWORD', config.get('password'))
    
    # Validate required config
    required_fields = ['workday_url', 'username', 'password']
    for field in required_fields:
        if not config.get(field):
            logger.error(f"Missing required config field: {field}. Set it in config.json or as environment variable.")
            return
    
    # Initialize and run scraper
    scraper = WorkdayFormMapper(config)
    
    try:
        await scraper.initialize_browser()
        logger.info("🚀 Starting Workday form extraction...")
        
        results = await scraper.crawl_and_extract()
        
        if results:
            output_file = scraper.export_results(args.output)
            
            print(f"\n✅ SUCCESS! Extracted {len(results)} form elements")
            print(f"📄 Results saved to: {output_file}")
            print(f"🌐 Pages visited: {len(scraper.visited_urls)}")
            
            # Print summary by type
            type_counts = {}
            for element in results:
                type_counts[element.type_of_input] = type_counts.get(element.type_of_input, 0) + 1
            
            print(f"\n📊 Form Elements by Type:")
            for form_type, count in sorted(type_counts.items()):
                print(f"   {form_type}: {count}")
            
            # Print sample results
            print(f"\n📋 Sample Results (first 3 elements):")
            for i, element in enumerate(results[:3]):
                print(f"\n{i+1}. {element.label}")
                print(f"   ID: {element.id_of_input_component}")
                print(f"   Type: {element.type_of_input}")
                print(f"   Required: {element.required}")
                if element.options:
                    print(f"   Options: {element.options}")
                if element.user_data_select_values:
                    print(f"   Sample Values: {element.user_data_select_values}")
        else:
            print("❌ No form elements extracted")
            print("Check the log file for detailed error information.")
            
    except Exception as e:
        logger.error(f"Scraper execution failed: {e}")
        logger.debug(traceback.format_exc())
        print(f"❌ Execution failed: {e}")
        
    finally:
        await scraper.cleanup()
        print("\n🧹 Cleanup completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
        logger.debug(traceback.format_exc())