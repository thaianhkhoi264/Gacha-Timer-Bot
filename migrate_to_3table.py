"""
Shadowverse Match Tracking: 2-Table to 3-Table Migration Script

This script migrates from the old 2-table architecture (winrates + matches)
to the new 3-table architecture (discord_matches + api_matches + combined_winrates).

The new architecture provides clean separation between Discord-logged and API-logged matches,
preventing cross-contamination during removals.

Usage:
    python migrate_to_3table.py --dry-run    # Preview migration without changes
    python migrate_to_3table.py --execute    # Perform actual migration
"""

import aiosqlite
import asyncio
import sys
import argparse
from datetime import datetime

async def check_table_exists(table_name):
    """
    Check if a table exists in the database.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        async with conn.execute('''
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        ''', (table_name,)) as cursor:
            return (await cursor.fetchone()) is not None


async def analyze_existing_matches():
    """
    Analyzes existing database structure and data.

    Returns: (has_matches_table, discord_count, api_count, total_count, winrates_count)
    - has_matches_table: True if matches table exists (current structure),
                        False if only winrates exists (old structure)
    """
    # Check if matches table exists
    has_matches = await check_table_exists('matches')

    if not has_matches:
        # Old database - only has winrates table, no individual match records
        print("  → Database has only 'winrates' table (old structure)")
        print("  → Individual match records not available")

        async with aiosqlite.connect('shadowverse_data.db') as conn:
            # Count winrate entries
            async with conn.execute('SELECT COUNT(*) FROM winrates') as cursor:
                winrates_count = (await cursor.fetchone())[0]

        print(f"  → Found {winrates_count} winrate entries (aggregated stats)")
        return False, 0, 0, 0, winrates_count

    # New database - has matches table with individual records
    print("  → Database has 'matches' table (current structure)")

    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # Count API matches (have metadata)
        async with conn.execute('''
            SELECT COUNT(*) FROM matches
            WHERE timestamp IS NOT NULL
               OR player_points IS NOT NULL
               OR player_rank IS NOT NULL
               OR player_group IS NOT NULL
               OR opponent_points IS NOT NULL
               OR opponent_rank IS NOT NULL
               OR opponent_group IS NOT NULL
        ''') as cursor:
            api_count = (await cursor.fetchone())[0]

        # Count Discord matches (no metadata)
        async with conn.execute('''
            SELECT COUNT(*) FROM matches
            WHERE timestamp IS NULL
              AND player_points IS NULL
              AND player_rank IS NULL
              AND player_group IS NULL
              AND opponent_points IS NULL
              AND opponent_rank IS NULL
              AND opponent_group IS NULL
        ''') as cursor:
            discord_count = (await cursor.fetchone())[0]

        # Count total
        async with conn.execute('SELECT COUNT(*) FROM matches') as cursor:
            total_count = (await cursor.fetchone())[0]

    return True, discord_count, api_count, total_count, 0


async def migrate_existing_data(has_matches_table):
    """
    Migrates data based on database structure.

    For new structure (has matches table):
        - API matches (with metadata) → api_matches
        - Discord matches (no metadata) → discord_matches

    For old structure (only winrates):
        - No individual matches to migrate (only aggregated stats exist)
    """
    if not has_matches_table:
        print("  Skipping individual match migration (no matches table)")
        return

    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # Migrate API matches (those with metadata)
        print("  Migrating API matches...")
        await conn.execute('''
            INSERT INTO api_matches (
                user_id, server_id, played_craft, opponent_craft, win, brick,
                timestamp, player_points, player_point_type, player_rank, player_group,
                opponent_points, opponent_point_type, opponent_rank, opponent_group,
                created_at
            )
            SELECT
                user_id, server_id, played_craft, opponent_craft, win, brick,
                timestamp, player_points, player_point_type, player_rank, player_group,
                opponent_points, opponent_point_type, opponent_rank, opponent_group,
                created_at
            FROM matches
            WHERE timestamp IS NOT NULL
               OR player_points IS NOT NULL
               OR player_rank IS NOT NULL
               OR player_group IS NOT NULL
               OR opponent_points IS NOT NULL
               OR opponent_rank IS NOT NULL
               OR opponent_group IS NOT NULL
        ''')

        # Migrate Discord matches (those without metadata)
        print("  Migrating Discord matches...")
        await conn.execute('''
            INSERT INTO discord_matches (
                user_id, server_id, played_craft, opponent_craft, win, brick, created_at
            )
            SELECT
                user_id, server_id, played_craft, opponent_craft, win, brick, created_at
            FROM matches
            WHERE timestamp IS NULL
              AND player_points IS NULL
              AND player_rank IS NULL
              AND player_group IS NULL
              AND opponent_points IS NULL
              AND opponent_rank IS NULL
              AND opponent_group IS NULL
        ''')

        await conn.commit()


async def rebuild_combined_winrates(has_matches_table):
    """
    Rebuilds combined_winrates based on database structure.

    For new structure (has matches table):
        - Aggregates from discord_matches and api_matches

    For old structure (only winrates):
        - Copies aggregated stats from winrates table
        - Treats all as Discord matches (no API data available)
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # Clear existing data
        await conn.execute('DELETE FROM combined_winrates')

        if not has_matches_table:
            # Old database - copy from winrates table
            print("  Copying winrates to combined_winrates (as Discord matches)...")
            await conn.execute('''
                INSERT INTO combined_winrates (
                    user_id, server_id, played_craft, opponent_craft,
                    discord_wins, discord_losses, discord_bricks,
                    api_wins, api_losses, api_bricks,
                    total_wins, total_losses, total_bricks
                )
                SELECT
                    user_id, server_id, played_craft, opponent_craft,
                    wins, losses, bricks,
                    0, 0, 0,
                    wins, losses, bricks
                FROM winrates
            ''')
            await conn.commit()
            return

        # New database - aggregate from matches tables
        # Get all unique user/server/craft combinations from both tables
        await conn.execute('''
            INSERT OR IGNORE INTO combined_winrates (
                user_id, server_id, played_craft, opponent_craft,
                discord_wins, discord_losses, discord_bricks,
                api_wins, api_losses, api_bricks,
                total_wins, total_losses, total_bricks
            )
            SELECT DISTINCT
                user_id, server_id, played_craft, opponent_craft,
                0, 0, 0, 0, 0, 0, 0, 0, 0
            FROM (
                SELECT user_id, server_id, played_craft, opponent_craft FROM discord_matches
                UNION
                SELECT user_id, server_id, played_craft, opponent_craft FROM api_matches
            )
        ''')

        # Update Discord stats
        print("  Aggregating Discord matches...")
        await conn.execute('''
            UPDATE combined_winrates
            SET discord_wins = (
                SELECT COUNT(*) FROM discord_matches d
                WHERE d.user_id = combined_winrates.user_id
                  AND d.server_id = combined_winrates.server_id
                  AND d.played_craft = combined_winrates.played_craft
                  AND d.opponent_craft = combined_winrates.opponent_craft
                  AND d.win = 1
            ),
            discord_losses = (
                SELECT COUNT(*) FROM discord_matches d
                WHERE d.user_id = combined_winrates.user_id
                  AND d.server_id = combined_winrates.server_id
                  AND d.played_craft = combined_winrates.played_craft
                  AND d.opponent_craft = combined_winrates.opponent_craft
                  AND d.win = 0
            ),
            discord_bricks = (
                SELECT COUNT(*) FROM discord_matches d
                WHERE d.user_id = combined_winrates.user_id
                  AND d.server_id = combined_winrates.server_id
                  AND d.played_craft = combined_winrates.played_craft
                  AND d.opponent_craft = combined_winrates.opponent_craft
                  AND d.brick = 1
            )
        ''')

        # Update API stats
        print("  Aggregating API matches...")
        await conn.execute('''
            UPDATE combined_winrates
            SET api_wins = (
                SELECT COUNT(*) FROM api_matches a
                WHERE a.user_id = combined_winrates.user_id
                  AND a.server_id = combined_winrates.server_id
                  AND a.played_craft = combined_winrates.played_craft
                  AND a.opponent_craft = combined_winrates.opponent_craft
                  AND a.win = 1
            ),
            api_losses = (
                SELECT COUNT(*) FROM api_matches a
                WHERE a.user_id = combined_winrates.user_id
                  AND a.server_id = combined_winrates.server_id
                  AND a.played_craft = combined_winrates.played_craft
                  AND a.opponent_craft = combined_winrates.opponent_craft
                  AND a.win = 0
            ),
            api_bricks = (
                SELECT COUNT(*) FROM api_matches a
                WHERE a.user_id = combined_winrates.user_id
                  AND a.server_id = combined_winrates.server_id
                  AND a.played_craft = combined_winrates.played_craft
                  AND a.opponent_craft = combined_winrates.opponent_craft
                  AND a.brick = 1
            )
        ''')

        # Update totals
        print("  Calculating combined totals...")
        await conn.execute('''
            UPDATE combined_winrates
            SET total_wins = discord_wins + api_wins,
                total_losses = discord_losses + api_losses,
                total_bricks = discord_bricks + api_bricks
        ''')

        await conn.commit()


async def archive_old_tables(has_matches_table):
    """
    Creates backup copies of old tables for verification and rollback.
    """
    async with aiosqlite.connect('shadowverse_data.db') as conn:
        # Check if backup tables already exist
        async with conn.execute('''
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='_backup_winrates'
        ''') as cursor:
            backup_exists = await cursor.fetchone()

        if backup_exists:
            print("  Backup tables already exist, skipping backup...")
            return

        # Create backup of matches table (if it exists)
        if has_matches_table:
            await conn.execute('''
                CREATE TABLE _backup_matches AS SELECT * FROM matches
            ''')
            print("  ✓ _backup_matches created")

        # Create backup of winrates table
        await conn.execute('''
            CREATE TABLE _backup_winrates AS SELECT * FROM winrates
        ''')
        print("  ✓ _backup_winrates created")

        await conn.commit()


async def verify_migration(has_matches_table):
    """
    Verifies that migration was successful by checking counts.

    Returns: (success, report_dict)
    """
    has_matches = await check_table_exists('matches')

    async with aiosqlite.connect('shadowverse_data.db') as conn:
        if has_matches:
            # New structure - verify individual match counts
            async with conn.execute('SELECT COUNT(*) FROM matches') as cursor:
                original_total = (await cursor.fetchone())[0]

            # Count new discord_matches
            async with conn.execute('SELECT COUNT(*) FROM discord_matches') as cursor:
                new_discord = (await cursor.fetchone())[0]

            # Count new api_matches
            async with conn.execute('SELECT COUNT(*) FROM api_matches') as cursor:
                new_api = (await cursor.fetchone())[0]

            # Verify total matches preserved
            new_total = new_discord + new_api
            success = (new_total == original_total)
        else:
            # Old structure - no individual matches to verify
            original_total = 0
            new_discord = 0
            new_api = 0
            new_total = 0
            success = True  # Success if combined_winrates was populated

        # Count combined_winrates rows
        async with conn.execute('SELECT COUNT(*) FROM combined_winrates') as cursor:
            winrate_rows = (await cursor.fetchone())[0]

        # Count original winrates
        async with conn.execute('SELECT COUNT(*) FROM winrates') as cursor:
            original_winrates = (await cursor.fetchone())[0]

        # For old structure, verify winrates were copied
        if not has_matches:
            success = (winrate_rows == original_winrates)

        report = {
            "has_matches_table": has_matches,
            "original_total": original_total,
            "new_discord": new_discord,
            "new_api": new_api,
            "new_total": new_total,
            "original_winrates": original_winrates,
            "winrate_rows": winrate_rows,
            "success": success
        }

        return success, report


async def run_migration(dry_run=True):
    """
    Executes the full migration from 2-table to 3-table architecture.

    Args:
        dry_run: If True, only analyzes data without making changes

    Returns:
        Migration report dictionary
    """
    print("=" * 60)
    print("SHADOWVERSE MATCH TRACKING MIGRATION")
    print("=" * 60)
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'EXECUTE (database will be modified)'}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Step 1: Analyze existing data
    print("Step 1: Analyzing existing data...")
    has_matches_table, discord_count, api_count, total_count, winrates_count = await analyze_existing_matches()

    if has_matches_table:
        print(f"  Found {total_count} total matches:")
        print(f"    - Discord matches (no metadata): {discord_count}")
        print(f"    - API matches (with metadata): {api_count}")
    else:
        print(f"  Found {winrates_count} winrate entries (aggregated stats)")
    print()

    if dry_run:
        print("=" * 60)
        print("DRY RUN COMPLETE - No changes made")
        print("=" * 60)
        print()
        print("To perform actual migration:")
        print("  1. BACKUP your database: cp shadowverse_data.db shadowverse_data.db.backup")
        print("  2. Run: python migrate_to_3table.py --execute")
        print()
        return {
            "dry_run": True,
            "has_matches_table": has_matches_table,
            "discord_count": discord_count,
            "api_count": api_count,
            "total_count": total_count,
            "winrates_count": winrates_count
        }

    # EXECUTE MODE - Make actual changes
    print("⚠️  WARNING: About to modify database!")
    print("   Press Ctrl+C within 5 seconds to cancel...")
    print()
    try:
        await asyncio.sleep(5)
    except KeyboardInterrupt:
        print("\nMigration cancelled by user.")
        sys.exit(0)

    # Step 2: Ensure new tables exist
    print("Step 2: Ensuring new tables exist...")
    from shadowverse_handler import init_sv_db
    await init_sv_db()
    print("  ✓ discord_matches")
    print("  ✓ api_matches")
    print("  ✓ combined_winrates")
    print()

    # Step 3: Migrate data
    print("Step 3: Migrating data...")
    await migrate_existing_data(has_matches_table)
    if has_matches_table:
        print(f"  ✓ Migrated {discord_count} Discord matches")
        print(f"  ✓ Migrated {api_count} API matches")
    else:
        print("  ✓ No individual matches to migrate")
    print()

    # Step 4: Rebuild aggregated stats
    print("Step 4: Rebuilding aggregated stats...")
    await rebuild_combined_winrates(has_matches_table)
    print("  ✓ combined_winrates populated")
    print()

    # Step 5: Archive old tables
    print("Step 5: Archiving old tables...")
    await archive_old_tables(has_matches_table)
    print()

    # Step 6: Verify migration
    print("Step 6: Verifying migration...")
    success, report = await verify_migration(has_matches_table)

    if report['has_matches_table']:
        print(f"  Original matches: {report['original_total']}")
        print(f"  New discord_matches: {report['new_discord']}")
        print(f"  New api_matches: {report['new_api']}")
        print(f"  New total: {report['new_total']}")
    else:
        print(f"  Original winrates: {report['original_winrates']}")
    print(f"  Combined winrate rows: {report['winrate_rows']}")
    print()

    print("=" * 60)
    if success:
        print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Test Discord match logging")
        if report['has_matches_table']:
            print("  2. Test API match logging")
            print("  3. Test Discord 'r' removal (should only affect Discord matches)")
            print("  4. Test API match removal (should only affect API matches)")
        else:
            print("  2. Test Discord 'r' removal")
        print("  5. Verify dashboard displays combined stats correctly")
        print()
        print("After verification (1-2 weeks):")
        if report['has_matches_table']:
            print("  - Drop old tables: DROP TABLE matches; DROP TABLE winrates;")
            print("  - Drop backup tables: DROP TABLE _backup_matches; DROP TABLE _backup_winrates;")
        else:
            print("  - Drop old tables: DROP TABLE winrates;")
            print("  - Drop backup tables: DROP TABLE _backup_winrates;")
        print()
    else:
        print("⚠️  MIGRATION COMPLETED WITH WARNINGS!")
        print("=" * 60)
        print()
        if report['has_matches_table']:
            print(f"  Count mismatch detected:")
            print(f"    Original: {report['original_total']}")
            print(f"    New total: {report['new_total']}")
        else:
            print(f"  Winrate mismatch detected:")
            print(f"    Original: {report['original_winrates']}")
            print(f"    New: {report['winrate_rows']}")
        print()
        print("  Please review the migration and verify data integrity.")
        print("  You can restore from backup if needed:")
        print("    cp shadowverse_data.db.backup shadowverse_data.db")
        print()

    return report


def main():
    parser = argparse.ArgumentParser(
        description='Migrate Shadowverse match tracking from 2-table to 3-table architecture'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview migration without making changes (default)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Perform actual migration (modifies database)'
    )

    args = parser.parse_args()

    # Default to dry-run if neither specified
    if not args.execute:
        args.dry_run = True

    # Run migration
    report = asyncio.run(run_migration(dry_run=args.dry_run))

    sys.exit(0 if report.get('success', True) else 1)


if __name__ == "__main__":
    main()
