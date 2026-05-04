import asyncio
import os
from datetime import datetime
from CategoryScraper import CategoryScraper
from S3Uploader import S3Uploader
import sys

# Add parent directory to path to import scraper_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scraper_utils import random_delay


class MainS3Scraper:
    """
    Main orchestrator for scraping Boshamlan data and uploading to Cloudflare R2.

    This script:
    1. Scrapes data from all categories (rent, sale, exchange) filtered by yesterday's date
    2. Creates Excel files with sheets for each subcategory
    3. Uploads files to R2 with date-based partitioning
    """
    
    def __init__(self, r2_access_key_id=None, r2_secret_access_key=None, r2_endpoint_url=None):
        """
        Initialize the main scraper.

        Args:
            r2_access_key_id: Cloudflare R2 access key (optional, can use environment variables)
            r2_secret_access_key: Cloudflare R2 secret key (optional, can use environment variables)
            r2_endpoint_url: Cloudflare R2 endpoint URL (optional, can use environment variables)
        """
        self.category_scraper = CategoryScraper()

        # Get R2 credentials from environment if not provided
        access_key = r2_access_key_id or os.environ.get('CF_R2_ACCESS_KEY_ID')
        secret_key = r2_secret_access_key or os.environ.get('CF_R2_SECRET_ACCESS_KEY')
        endpoint_url = r2_endpoint_url or os.environ.get('CF_R2_ENDPOINT_URL')

        self.s3_uploader = S3Uploader(
            bucket_name='data-collection-dl',
            r2_access_key_id=access_key,
            r2_secret_access_key=secret_key,
            r2_endpoint_url=endpoint_url
        )
    
    async def run(self):
        """
        Main execution method:
        1. Scrapes all categories and subcategories
        2. Uploads images to S3 in 'images' folder
        3. Creates Excel files with image_r2_path column
        4. Uploads Excel files to S3 in 'excel files' folder
        """
        print("="*80)
        print("BOSHAMLAN SCRAPER - Cloudflare R2 Edition")
        print("="*80)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Target R2: r2://data-collection-dl/boshamlan-data/properties/")
        print("  - Excel files -> year=YYYY/month=MM/day=DD/excel files/")
        print("  - Images -> year=YYYY/month=MM/day=DD/images/")
        print("="*80)

        # Step 1: Log R2 target
        print("\n[1/4] Connecting to R2 bucket...")
        print(f"✓ Using bucket: '{self.s3_uploader.bucket_name}'")
        
        # Step 2: Scrape all categories (don't save Excel yet)
        print("\n[2/4] Scraping data from all categories...")
        # First scrape without saving to Excel
        for category_name in self.category_scraper.categories.keys():
            print(f"\n{'#'*70}")
            print(f"# Scraping Category: {category_name.upper()}")
            print(f"{'#'*70}\n")
            
            await self.category_scraper.scrape_category(category_name)
            # Random delay between categories (2-4 seconds)
            await random_delay(2.0, 4.0)
        
        if not self.category_scraper.last_scraped_data:
            print("WARNING: No data was scraped. Nothing to upload.")
            return
        
        print(f"\n✓ Successfully scraped {len(self.category_scraper.last_scraped_data)} category(ies)")
        
        # Step 3: Upload images to S3 and get mappings
        print("\n[3/4] Uploading images to S3...")
        image_s3_mappings = {}
        total_images = 0
        
        for category_name, category_data in self.category_scraper.last_scraped_data.items():
            # Get all cards data for this category
            all_cards = []
            for subcat_name, subcat_data in category_data.items():
                all_cards.extend(subcat_data)
            
            if all_cards:
                image_results = await self.s3_uploader.upload_images_from_data(all_cards, category_name)
                image_s3_mappings[category_name] = image_results
                total_images += len(image_results)
        
        print(f"\n\u2713 Successfully uploaded {total_images} image(s) to R2")
        
        # Step 4: Create Excel files with image_r2_path column
        print("\n[4/4] Creating and uploading Excel files...")
        excel_files = {}
        
        for category_name, category_data in self.category_scraper.last_scraped_data.items():
            category_image_mapping = image_s3_mappings.get(category_name, {})
            file_path = self.category_scraper.save_to_excel(category_name, category_data, category_image_mapping)
            if file_path:
                excel_files[category_name] = file_path
        
        if not excel_files:
            print("WARNING: No Excel files were generated.")
            return
        
        print(f"\n\u2713 Successfully created {len(excel_files)} Excel file(s)")

        # Upload Excel files to R2
        upload_results = self.s3_uploader.upload_multiple_files(excel_files)

        if upload_results:
            print(f"\n\u2713 Successfully uploaded {len(upload_results)} Excel file(s) to R2:")
            for category, r2_uri in upload_results.items():
                print(f"  - {category}: {r2_uri}")
        else:
            print("\nERROR: Failed to upload Excel files to R2.")
        
        # Summary
        print("\n" + "="*80)
        print("SCRAPING COMPLETED")
        print("="*80)
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Categories processed: {len(excel_files)}")
        print(f"Images uploaded to R2: {total_images}")
        print(f"Excel files uploaded to R2: {len(upload_results)}")
        print("="*80)


async def main():
    """
    Entry point for the scraper.

    Cloudflare R2 credentials must be provided via environment variables:
      CF_R2_ACCESS_KEY_ID, CF_R2_SECRET_ACCESS_KEY, CF_R2_ENDPOINT_URL
    """
    # Credentials are read from CF_R2_* environment variables
    scraper = MainS3Scraper()

    await scraper.run()


if __name__ == "__main__":
    """
    Usage:

    Set environment variables (required):
       export CF_R2_ACCESS_KEY_ID=your-r2-access-key
       export CF_R2_SECRET_ACCESS_KEY=your-r2-secret-key
       export CF_R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
       python main_s3.py

    For Windows PowerShell:
       $env:CF_R2_ACCESS_KEY_ID="your-r2-access-key"
       $env:CF_R2_SECRET_ACCESS_KEY="your-r2-secret-key"
       $env:CF_R2_ENDPOINT_URL="https://<account_id>.r2.cloudflarestorage.com"
       python main_s3.py
    """
    asyncio.run(main())
