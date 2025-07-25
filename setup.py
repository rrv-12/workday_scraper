import json
import os
import getpass
import sys

def create_config():
    """Interactive configuration setup"""
    print("🚀 Workday Form Scraper - Setup")
    print("=" * 40)
    
    # Get Workday URL
    print("\n1. First, find your Workday URL:")
    print("   - Go to your company's Workday careers page")
    print("   - Copy the URL from your browser")
    print("   - It usually looks like: https://companyname.myworkdayjobs.com/External")
    
    workday_url = input("\n📋 Enter your Workday URL: ").strip()
    
    if not workday_url.startswith('http'):
        print("❌ URL should start with https://")
        return False
    
    # Get credentials
    print("\n2. Now enter your login credentials:")
    username = input("📧 Email/Username: ").strip()
    
    # Use getpass to hide password input
    password = getpass.getpass("🔒 Password: ")
    
    if not username or not password:
        print("❌ Username and password are required")
        return False
    
    # Optional settings
    print("\n3. Optional settings (press Enter for defaults):")
    
    headless_input = input("🖥️  Run in headless mode? (y/n) [y]: ").strip().lower()
    headless = headless_input != 'n'
    
    max_pages_input = input("📄 Maximum pages to crawl [10]: ").strip()
    try:
        max_pages = int(max_pages_input) if max_pages_input else 10
    except ValueError:
        max_pages = 10
    
    # Create config dictionary
    config = {
        "workday_url": workday_url,
        "username": username,
        "password": password,
        "headless": headless,
        "slow_mo": 100,
        "max_pages": max_pages,
        "timeout": 30000,
        "wait_between_pages": 2000
    }
    
    # Save to file
    try:
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        print("\n✅ Configuration saved to config.json")
        print("\n🔐 Security Note:")
        print("   Your password is stored in plain text in config.json")
        print("   For better security, delete config.json after use and use environment variables:")
        print(f"   export WORKDAY_URL='{workday_url}'")
        print(f"   export WORKDAY_USERNAME='{username}'")
        print(f"   export WORKDAY_PASSWORD='your_password'")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving configuration: {e}")
        return False

def main():
    """Main setup function"""
    if os.path.exists('config.json'):
        overwrite = input("⚠️  config.json already exists. Overwrite? (y/n): ").strip().lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return
    
    if create_config():
        print("\n🎉 Setup complete! You can now run:")
        print("   python workday_scraper.py --config config.json")
    else:
        print("\n❌ Setup failed. Please try again.")

if __name__ == "__main__":
    main()