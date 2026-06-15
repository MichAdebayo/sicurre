import asyncio
import sys
from uuid import UUID
from core.database import AsyncSessionFactory
from core.config import get_settings
from data_platform.services.dataset_publish import DatasetPublishService
from db.queries.records import DatasetQueries

async def main():
    settings = get_settings()
    publish_service = DatasetPublishService(settings=settings)
    queries = DatasetQueries()
    
    async with AsyncSessionFactory() as session:
        # Get all datasets and find the latest frozen one
        datasets, total = await queries.list(session, limit=10, offset=0, status=None)
        
        frozen_datasets = [d for d in datasets if d.status == 'frozen']
        if not frozen_datasets:
            print("No frozen datasets found.")
            sys.exit(1)
            
        print("Found frozen datasets:")
        for d in frozen_datasets:
            print(f"- ID: {d.id}, Tag: {d.version_tag}, Status: {d.status}, Count: {d.item_count}")
            
        target_tag = "cron-20260615-111107"
        target_dataset = next((d for d in frozen_datasets if d.version_tag == target_tag), None)
        
        if not target_dataset:
            print(f"Could not find frozen dataset with tag {target_tag}")
            target_dataset = frozen_datasets[0]
            print(f"Falling back to latest dataset: {target_dataset.version_tag}")
            
        print(f"Publishing dataset: {target_dataset.version_tag} ({target_dataset.id})")
        from data_platform.services.dataset_publish import GitHubDispatchPublishError
        try:
            result = await publish_service.publish(session, target_dataset.id)
            print("\n============================================================")
            print("Publish successful!")
            print(f"Kaggle URL: {result.kaggle_url}")
            print(f"Kaggle Version ID: {result.kaggle_version_id}")
            print(f"GitHub Actions Dispatch Sent: {result.github_dispatch_sent}")
            print("============================================================")
        except GitHubDispatchPublishError as e:
            print("\n============================================================")
            print("Kaggle Publish Succeeded, but GitHub Dispatch Failed!")
            print(f"Kaggle Version ID: {e.kaggle_version_id}")
            print(f"Kaggle URL: https://www.kaggle.com/datasets/{e.kaggle_slug}/versions/{e.kaggle_version_id}")
            print(f"GitHub Dispatch Error detail: {e}")
            print("This is expected if the 'sicurre-ml' repository is not created yet or not accessible.")
            print("============================================================")
        except Exception as e:
            print(f"\nPublish failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
