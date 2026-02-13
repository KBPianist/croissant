import os
import zipfile
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import logging
from typing import List, Optional, Tuple
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('parquet_conversion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ZipToParquetConverter:
    def __init__(
            self,
            input_folders: List[str],
            chunk_size: int = 100000,
            max_workers: int = 4,
            compression: str = 'zstd',
            row_group_size: int = 100000,
            cleanup_csv: bool = True
    ):
        """
        Initialize the converter

        Args:
            input_folders: List of folders containing zip files
            chunk_size: Number of rows per chunk when reading CSV
            max_workers: Maximum number of threads
            compression: Parquet compression algorithm
            row_group_size: Parquet row group size
            cleanup_csv: Whether to delete CSV files after conversion
        """
        self.input_folders = [Path(folder) for folder in input_folders]
        self.chunk_size = chunk_size
        self.max_workers = max_workers
        self.compression = compression
        self.row_group_size = row_group_size
        self.cleanup_csv = cleanup_csv

        # Validate all input folders
        for folder in self.input_folders:
            if not folder.exists():
                logger.warning(f"Folder does not exist: {folder}")

    def find_zip_files(self) -> List[Path]:
        """Find all zip files in input folders"""
        zip_files = []
        for folder in self.input_folders:
            if folder.exists():
                # Recursively find all zip files
                for zip_file in folder.rglob("*.zip"):
                    zip_files.append(zip_file)
            else:
                logger.warning(f"Folder does not exist: {folder}")

        logger.info(f"Found {len(zip_files)} zip files")
        return zip_files

    def extract_zip_to_same_folder(self, zip_path: Path) -> Optional[Path]:
        """Extract zip file to the same directory"""
        try:
            # Create extraction directory (using zip filename without .zip extension)
            extract_dir = zip_path.parent / zip_path.stem

            # Skip if already extracted
            if extract_dir.exists():
                logger.info(f"Extraction directory already exists: {extract_dir}")
                return extract_dir

            logger.info(f"Extracting: {zip_path}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            logger.info(f"Extraction completed: {extract_dir}")
            return extract_dir

        except zipfile.BadZipFile:
            logger.error(f"Corrupted zip file: {zip_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract {zip_path}: {e}")
            return None

    def find_csv_files(self, directory: Path) -> List[Path]:
        """Find all CSV files in directory (including subdirectories)"""
        return list(directory.rglob("*.csv"))

    def convert_csv_to_parquet_single_file(self, csv_path: Path) -> Tuple[bool, int, int]:
        """
        Convert CSV file to a single parquet file with multiple row groups

        Returns:
            (success, total_rows, row_groups)
        """
        try:
            # Output to same directory, replacing .csv with .parquet
            output_file = csv_path.with_suffix('.parquet')

            # Skip if target file already exists
            if output_file.exists():
                logger.info(f"Parquet file already exists: {output_file}")
                # Read existing file info
                try:
                    parquet_file = pq.ParquetFile(output_file)
                    return True, parquet_file.metadata.num_rows, parquet_file.metadata.num_row_groups
                except:
                    pass

            logger.info(f"Starting conversion: {csv_path}")

            # Create Parquet writer
            writer = None
            total_rows = 0
            row_group_count = 0

            try:
                # Read CSV in chunks and write to parquet
                for i, chunk in enumerate(pd.read_csv(
                        csv_path,
                        sep=',',
                        chunksize=self.chunk_size,
                        low_memory=False,
                        encoding='utf-8',
                        on_bad_lines='warn'
                )):
                    if len(chunk) == 0:
                        continue

                    total_rows += len(chunk)

                    # Convert to Arrow Table
                    table = pa.Table.from_pandas(chunk)

                    # If first chunk, create writer and save schema
                    if writer is None:
                        writer = pq.ParquetWriter(
                            output_file,
                            schema=table.schema,
                            compression=self.compression,
                            version='2.6',
                            row_group_size=self.row_group_size
                        )
                        logger.info(f"  Created Parquet writer: {output_file}")

                    # Write current chunk as row group
                    writer.write_table(table)
                    row_group_count += 1

                    if (i + 1) % 10 == 0:  # Log progress every 10 chunks
                        logger.info(f"  Processed {i + 1} chunks, {total_rows:,} rows, {row_group_count} row groups")

                # Close writer
                if writer:
                    writer.close()
                    logger.info(f"Conversion completed: {csv_path} -> {output_file}")
                    logger.info(f"  Total rows: {total_rows:,}, Row groups: {row_group_count}")
                    return True, total_rows, row_group_count
                else:
                    logger.warning(f"CSV file is empty: {csv_path}")
                    return False, 0, 0

            except UnicodeDecodeError:
                logger.warning(f"Encoding failed, trying GBK: {csv_path}")
                return self.retry_csv_with_gbk(csv_path, ',', output_file)
            except Exception as e:
                logger.error(f"CSV processing failed {csv_path}: {e}")
                # Ensure writer is closed
                if writer:
                    writer.close()
                    # Delete potentially corrupted output file
                    if output_file.exists():
                        output_file.unlink()
                return False, 0, 0

        except Exception as e:
            logger.error(f"Conversion failed {csv_path}: {e}")
            return False, 0, 0

    def retry_csv_with_gbk(self, csv_path: Path, delimiter: str, output_file: Path) -> Tuple[bool, int, int]:
        """Retry conversion with GBK encoding"""
        writer = None
        total_rows = 0
        row_group_count = 0

        try:
            for i, chunk in enumerate(pd.read_csv(
                    csv_path,
                    sep=delimiter,
                    chunksize=self.chunk_size,
                    low_memory=False,
                    encoding='gbk',
                    on_bad_lines='warn'
            )):
                if len(chunk) == 0:
                    continue

                total_rows += len(chunk)
                table = pa.Table.from_pandas(chunk)

                if writer is None:
                    writer = pq.ParquetWriter(
                        output_file,
                        schema=table.schema,
                        compression=self.compression,
                        version='2.6',
                        row_group_size=self.row_group_size
                    )
                    logger.info(f"  Recreated Parquet writer with GBK encoding")

                writer.write_table(table)
                row_group_count += 1

                if (i + 1) % 10 == 0:
                    logger.info(f"  Processed {i + 1} chunks, {total_rows:,} rows")

            if writer:
                writer.close()
                logger.info(f"GBK conversion completed: {csv_path} -> {output_file}")
                logger.info(f"  Total rows: {total_rows:,}, Row groups: {row_group_count}")
                return True, total_rows, row_group_count
            else:
                return False, 0, 0

        except Exception as e:
            logger.error(f"GBK encoding also failed {csv_path}: {e}")
            if writer:
                writer.close()
            if output_file.exists():
                output_file.unlink()
            return False, 0, 0

    def delete_csv_file(self, csv_path: Path) -> bool:
        """Delete CSV file"""
        try:
            if csv_path.exists():
                csv_path.unlink()
                logger.info(f"Deleted CSV file: {csv_path}")
                return True
            else:
                logger.warning(f"CSV file does not exist: {csv_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete CSV file {csv_path}: {e}")
            return False

    def process_single_csv(self, csv_path: Path) -> dict:
        """Process single CSV file (delete immediately after conversion)"""
        result = {
            'csv_file': str(csv_path),
            'success': False,
            'total_rows': 0,
            'row_groups': 0,
            'output_file': None,
            'csv_deleted': False,
            'error': None
        }

        try:
            # Step 1: Convert CSV to Parquet
            success, total_rows, row_groups = self.convert_csv_to_parquet_single_file(csv_path)

            result['success'] = success
            result['total_rows'] = total_rows
            result['row_groups'] = row_groups

            if success:
                output_file = csv_path.with_suffix('.parquet')
                result['output_file'] = str(output_file)

                # Step 2: Immediately delete original CSV file (if enabled)
                if self.cleanup_csv:
                    csv_deleted = self.delete_csv_file(csv_path)
                    result['csv_deleted'] = csv_deleted
            else:
                result['error'] = "Conversion failed"

        except Exception as e:
            logger.error(f"Exception processing CSV file {csv_path}: {e}")
            result['error'] = str(e)

        return result

    def process_zip_file(self, zip_path: Path) -> dict:
        """Process single zip file"""
        result = {
            'zip_file': str(zip_path),
            'success': False,
            'csv_files': 0,
            'converted': 0,
            'deleted': 0,
            'total_rows': 0,
            'total_row_groups': 0,
            'errors': []
        }

        try:
            # Step 1: Extract zip file to same directory
            extract_dir = self.extract_zip_to_same_folder(zip_path)
            if not extract_dir:
                result['errors'].append("Extraction failed")
                return result

            # Step 2: Find CSV files
            csv_files = self.find_csv_files(extract_dir)
            result['csv_files'] = len(csv_files)

            if not csv_files:
                logger.warning(f"No CSV files found: {extract_dir}")
                result['errors'].append("No CSV files found")
                return result

            logger.info(f"Found {len(csv_files)} CSV files to process")

            # Step 3: Convert CSV to Parquet (using thread pool)
            successful_conversions = 0
            deleted_files = 0

            # Use thread pool to process CSV files
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(csv_files))) as executor:
                future_to_csv = {
                    executor.submit(self.process_single_csv, csv_file): csv_file
                    for csv_file in csv_files
                }

                for future in as_completed(future_to_csv):
                    csv_file = future_to_csv[future]
                    try:
                        csv_result = future.result()

                        if csv_result['success']:
                            successful_conversions += 1
                            result['total_rows'] += csv_result['total_rows']
                            result['total_row_groups'] += csv_result['row_groups']

                            if csv_result['csv_deleted']:
                                deleted_files += 1

                            logger.info(
                                f"  ✓ {csv_file.name}: {csv_result['total_rows']:,} rows, {csv_result['row_groups']} row groups")

                            # Show deletion status
                            if csv_result['csv_deleted']:
                                logger.info(f"    CSV file deleted")
                            else:
                                logger.info(f"    CSV file retained (cleanup_csv={self.cleanup_csv})")

                        else:
                            error_msg = csv_result.get('error', 'Unknown error')
                            result['errors'].append(f"{csv_file.name}: {error_msg}")
                            logger.error(f"  ✗ {csv_file.name}: {error_msg}")

                    except Exception as e:
                        error_msg = f"Processing exception: {e}"
                        result['errors'].append(f"{csv_file.name}: {error_msg}")
                        logger.error(f"  ✗ {csv_file.name}: {error_msg}")

            result['converted'] = successful_conversions
            result['deleted'] = deleted_files
            result['success'] = successful_conversions == len(csv_files)

            # Note: Do NOT clean up extraction directory! Keep extracted directory and any other files

        except Exception as e:
            logger.error(f"Failed to process zip file {zip_path}: {e}")
            result['errors'].append(f"Processing failed: {e}")

        return result

    def run(self):
        """Main execution function"""
        logger.info("=" * 60)
        logger.info("ZIP to Parquet Batch Conversion")
        logger.info(f"Input folders: {[str(f) for f in self.input_folders]}")
        logger.info(f"Worker threads: {self.max_workers}")
        logger.info(f"Read chunk size: {self.chunk_size:,}")
        logger.info(f"Parquet row group size: {self.row_group_size:,}")
        logger.info(f"Compression algorithm: {self.compression}")
        logger.info(f"Delete CSV after conversion: {self.cleanup_csv}")
        logger.info("=" * 60)

        start_time = time.time()

        # Find all zip files
        zip_files = self.find_zip_files()

        if not zip_files:
            logger.warning("No zip files found!")
            return []

        # Use thread pool to process zip files
        all_results = []
        total_processed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_zip = {
                executor.submit(self.process_zip_file, zip_file): zip_file
                for zip_file in zip_files
            }

            for future in as_completed(future_to_zip):
                zip_file = future_to_zip[future]
                try:
                    zip_result = future.result()
                    all_results.append(zip_result)
                    total_processed += 1

                    # Show processing progress
                    status = "✓" if zip_result['success'] else "✗"
                    logger.info(f"[{total_processed}/{len(zip_files)}] {status} {zip_file.name}")
                    logger.info(f"  CSV files: {zip_result['csv_files']}, Converted: {zip_result['converted']}")
                    logger.info(f"  CSV deleted: {zip_result['deleted']}, Total rows: {zip_result['total_rows']:,}")

                    if not zip_result['success'] and zip_result['errors']:
                        logger.warning(f"  Error: {zip_result['errors'][0]}")
                        if len(zip_result['errors']) > 1:
                            logger.warning(f"  Plus {len(zip_result['errors']) - 1} more errors...")

                    logger.info("-" * 40)

                except Exception as e:
                    logger.error(f"Exception processing zip file {zip_file}: {e}")

        # Calculate statistics
        elapsed_time = time.time() - start_time
        successful_zips = sum(1 for r in all_results if r['success'])
        total_csv_files = sum(r['csv_files'] for r in all_results)
        total_converted = sum(r['converted'] for r in all_results)
        total_deleted = sum(r['deleted'] for r in all_results)
        total_rows = sum(r['total_rows'] for r in all_results)

        logger.info("=" * 60)
        logger.info("Processing completed!")
        logger.info(f"Total time: {elapsed_time:.2f} seconds ({elapsed_time / 60:.2f} minutes)")
        logger.info(f"Total ZIP files processed: {len(zip_files)}")
        logger.info(f"Successfully processed ZIP files: {successful_zips}")
        logger.info(f"Total CSV files: {total_csv_files}")
        logger.info(f"Successfully converted CSV files: {total_converted}")
        logger.info(f"Deleted CSV files: {total_deleted}")
        logger.info(f"Total data rows: {total_rows:,}")
        logger.info(f"ZIP success rate: {successful_zips / len(zip_files) * 100:.1f}%")
        logger.info(f"CSV conversion success rate: {total_converted / total_csv_files * 100:.1f}%")
        if self.cleanup_csv:
            logger.info(
                f"CSV deletion rate: {total_deleted / total_converted * 100:.1f}%" if total_converted > 0 else "CSV deletion rate: N/A")
        logger.info("=" * 60)

        # Save detailed processing results
        self.save_detailed_results(all_results, elapsed_time)

        return all_results

    def save_detailed_results(self, results: List[dict], elapsed_time: float):
        """Save detailed processing results to CSV"""
        try:
            # Prepare data
            summary_data = []
            for result in results:
                summary_data.append({
                    'zip_file': result['zip_file'],
                    'csv_files': result['csv_files'],
                    'converted': result['converted'],
                    'deleted': result['deleted'],
                    'success': result['success'],
                    'total_rows': result['total_rows'],
                    'total_row_groups': result['total_row_groups'],
                    'errors': '; '.join(result['errors']) if result['errors'] else ''
                })

            # Save to current directory
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            results_file = Path(f"conversion_summary_{timestamp}.csv")

            df = pd.DataFrame(summary_data)
            df.to_csv(results_file, index=False, encoding='utf-8')
            logger.info(f"Processing results saved to: {results_file}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")


# Simplified usage function
def convert_zips_to_parquet(
        folders: List[str],
        max_workers: int = 4,
        cleanup_csv: bool = True,
        chunk_size: int = 100000
):
    """
    Quick conversion function

    Args:
        folders: List of folders containing zip files
        max_workers: Number of worker threads
        cleanup_csv: Whether to delete CSV after conversion
        chunk_size: Read chunk size
    """
    # Filter out non-existent folders
    valid_folders = [f for f in folders if os.path.exists(f)]

    if not valid_folders:
        print(f"Error: None of the specified folders exist")
        print(f"Checked folders: {folders}")
        return

    print(f"Starting to process {len(valid_folders)} folders...")

    converter = ZipToParquetConverter(
        input_folders=valid_folders,
        chunk_size=chunk_size,
        max_workers=max_workers,
        compression='zstd',
        row_group_size=chunk_size,
        cleanup_csv=cleanup_csv
    )

    return converter.run()


def main():
    """Main function example"""
    # Configure folders to process (modify to your actual paths)
    input_folders = [
        "C:/baidunetdiskdownload/2025",
        "C:/baidunetdiskdownload/2023"
        # Add more folders...
    ]

    # Use quick conversion function
    results = convert_zips_to_parquet(
        folders=input_folders,
        max_workers=4,
        cleanup_csv=True,
        chunk_size=50000
    )

    if results:
        print(f"Processing completed! Processed {len(results)} ZIP files")

if __name__ == "__main__":
    main()