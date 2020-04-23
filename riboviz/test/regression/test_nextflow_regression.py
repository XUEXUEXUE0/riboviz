"""
:py:mod:`riboviz.tools.prep_riboviz` regression test suite.

The regression test suite runs Nextflow on ``prep_riboviz.nf`` using a
given configuration file, then compares the results to a directory of
pre-calculated results, specified by the user.

Usage::

    pytest riboviz/test/regression/test_regression.py
      --expected=DIRECTORY
      [--skip-workflow]
      [--check-index-tmep]
      [--config-file=FILE]

The test suite accepts the following command-line parameters:

* ``--expected``: Directory with expected data files, against which
  files specified in the configuration file (see below) will be
  checked.
* ``--skip-workflow``: Workflow will not be run prior to checking data
  files. This can be used to check existing files generated by a run
  of the workflow.
* ``--check-index-tmp``: Check index and temporary files (default is
  that only the output files are checked).
* ``--config-file``: Configuration file. If provided then the index,
  temporary and output directories specified in this file will be
  validated against those specified by ``--expected``. If not provided
  then the file :py:const:`riboviz.test.VIGNETTE_CONFIG` will be
  used. The configuration file must specify demultiplexed samples
  (i.e. it should use :py:const:`riboviz.params.FQ_FILES` and not
  :py:const:`riboviz.params.MULTIPLEX_FQ_FILES`).

As the expected data directories and those with the data to be tested
may vary in their paths the following approach is used:

* The paths of the directories with the data to be tested are taken to
  be those specified in the configuration file.
* The paths of the directories with the expected data are taken to be
  relative to the ``--expected`` directory and to share common names
  with the final directories of each path of the actual data
  directories.

For example, if the configuration file has::

    dir_index: vignette/index
    dir_out: vignette/simdata_umi_output
    dir_tmp: vignette/simdata_umi_tmp

and ``--expected`` is ``/home/user/simdata-umi-data`` then directories
with the data to be tested are::

    vignette/index
    vignette/simdata_umi_output
    vignette/simdata_umi_tmp

and the directories with the expected data are::

    /home/user/simdata-umi-data/index
    /home/user/simdata-umi-data/simdata_umi_output
    /home/user/simdata-umi-data/simdata_umi_tmp

If running with a configuration that used UMI extraction,
deduplication and grouping then note that:

* UMI deduplication statistics files are not checked (files prefixed
  by :py:const:`riboviz.workflow_files.DEDUP_STATS_PREFIX`).
* UMI group file post-deduplication files are not checked
  (:py:const:`riboviz.workflow_files.POST_DEDUP_GROUPS_TSV`). These
  files can differ between runs depending on which reads are removed
  by  ``umi_tools dedup``.
* BAM file output by deduplication (``dedup.bam`` and
  ``SAMPLE.bam``) can differ between runs depending on which reads are
  removed by ``umi_tools dedup``. Only the existence of these files
  is checked.

See :py:mod:`riboviz.test.regression.conftest` for information on the
fixtures used by these tests.
"""
import os
import shutil
import tempfile
import pytest
import pysam
from riboviz import h5
from riboviz import hisat2
from riboviz import sam_bam
from riboviz import compare_files
from riboviz import count_reads
from riboviz import process_utils
from riboviz import workflow_files
from riboviz import workflow_r
from riboviz import test


@pytest.fixture(scope="module")
def nextflow_fixture(skip_workflow_fixture, config_fixture):
    """
    Run ``nextflow run prep_riboviz.ng``  if ``skip_workflow_fixture``
    is not ``True``.

    :param skip_workflow_fixture: Should workflow not be run?
    :type skip_workflow_fixture: bool
    :param config_fixture: Configuration file
    :type config_fixture: str or unicode
    """
    if not skip_workflow_fixture:
        cmd = ["nextflow", "run", "prep_riboviz.nf", "-params-file",
               config_fixture, "-ansi-log", "false"]
        process_utils.run_command(cmd)
        # Will raise AssertionError if non-zero exit code.


@pytest.fixture(scope="function")
def scratch_directory():
    """
    Create a scratch directory.

    :return: directory
    :rtype: str or unicode
    """
    scratch_dir = tempfile.mkdtemp("tmp_scratch")
    yield scratch_dir
    shutil.rmtree(scratch_dir)


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("index", list(range(1, test.NUM_INDICES)))
def test_hisat2_build_index_files(expected_fixture, index_dir,
                                  index_prefix, index):
    """
    Test ``hisat2-build`` index files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param index_dir: Index files directory, from configuration file
    :type index_dir: str or unicode
    :param index_prefix: Index file name prefix
    :type index_prefix: str or unicode
    :param index: File name index
    :type index: int
    """
    file_name = hisat2.HT2_FORMAT.format(index_prefix, index)
    index_dir_name = os.path.basename(os.path.normpath(index_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, index_dir_name, file_name),
        os.path.join(index_dir, file_name))


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.ADAPTER_TRIM_FQ])
def test_cutadapt_fq_files(expected_fixture, tmp_dir, sample,
                           file_name):
    """
    Test ``cutadapt`` FASTQ files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    tmp_dir_name = os.path.basename(os.path.normpath(tmp_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, tmp_dir_name, sample,
                     file_name),
        os.path.join(tmp_dir, sample, file_name))


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.UMI_EXTRACT_FQ])
def test_umitools_extract_fq(extract_umis, expected_fixture, tmp_dir,
                             sample, file_name):
    """
    Test ``umi_tools extract`` FASTQ files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    If UMI extraction was not enabled in the configuration that
    produced the data then this test is skipped.

    :param extract_umi: Was UMI extraction configured?
    :type extract_umis: bool
    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    if not extract_umis:
        pytest.skip('Skipped test applicable to UMI extraction')
    tmp_dir_name = os.path.basename(os.path.normpath(tmp_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, tmp_dir_name, sample,
                     file_name),
        os.path.join(tmp_dir, sample, file_name))


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.NON_RRNA_FQ,
    workflow_files.UNALIGNED_FQ])
def test_hisat_fq_files(expected_fixture, tmp_dir, sample, file_name):
    """
    Test ``hisat`` FASTQ files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    tmp_dir_name = os.path.basename(os.path.normpath(tmp_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, tmp_dir_name, sample,
                     file_name),
        os.path.join(tmp_dir, sample, file_name))


def compare_sam_files(expected_directory, directory,
                      scratch_directory, sample, file_name):
    """
    Test SAM files for equality. The SAM files are sorted
    into temporary SAM files which are then compared. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_directory: Expected data directory
    :type expected_directory: str or unicode
    :param directory: Data directory
    :type directory: str or unicode
    :param scratch_directory: scratch files directory
    :type scratch_directory: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    dir_name = os.path.basename(os.path.normpath(directory))
    expected_file = os.path.join(
        expected_directory, dir_name, sample, file_name)
    actual_file = os.path.join(directory, sample, file_name)
    expected_copy_dir = os.path.join(scratch_directory, "expected")
    os.mkdir(expected_copy_dir)
    actual_copy_dir = os.path.join(scratch_directory, "actual")
    os.mkdir(actual_copy_dir)
    expected_copy_file = os.path.join(expected_copy_dir, file_name)
    actual_copy_file = os.path.join(actual_copy_dir, file_name)
    pysam.sort("-o", expected_copy_file, expected_file)
    pysam.sort("-o", actual_copy_file, actual_file)
    compare_files.compare_files(expected_copy_file, actual_copy_file)


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.ORF_MAP_SAM,
    workflow_files.RRNA_MAP_SAM])
def test_hisat2_sam_files(expected_fixture, tmp_dir,
                          scratch_directory, sample, file_name):
    """
    Test ``hisat`` SAM files for equality. The SAM files are sorted
    into temporary SAM files which are then compared. See
    :py:func:`compare_sam_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param scratch_directory: scratch files directory
    :type scratch_directory: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    compare_sam_files(expected_fixture, tmp_dir, scratch_directory,
                      sample, file_name)


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.ORF_MAP_CLEAN_SAM])
def test_trim5p_mismatch_sam_files(expected_fixture, tmp_dir,
                                   scratch_directory, sample,
                                   file_name):
    """
    Test :py:mod:`riboviz.tools.trim_5p_mismatch` SAM files for
    equality. The SAM files are sorted into temporary SAM files which
    are then compared. See
    :py:func:`compare_files.compare_sam_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param scratch_directory: scratch files directory
    :type scratch_directory: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    compare_sam_files(expected_fixture, tmp_dir, scratch_directory,
                      sample, file_name)


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.TRIM_5P_MISMATCH_TSV])
def test_trim5p_mismatch_tsv_files(expected_fixture, tmp_dir,
                                   sample, file_name):
    """
    Test :py:mod:`riboviz.tools.trim_5p_mismatch` TSV files for
    equality. See :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    tmp_dir_name = os.path.basename(os.path.normpath(tmp_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, tmp_dir_name, sample,
                     file_name),
        os.path.join(tmp_dir, sample, file_name))


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [workflow_files.ORF_MAP_CLEAN_BAM])
def test_samtools_view_sort_index_tmp(expected_fixture, tmp_dir,
                                      sample, file_name):
    """
    Test ``samtools view | samtools sort`` BAM and ``samtools index``
    BAI files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    tmp_dir_name = os.path.basename(os.path.normpath(tmp_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, tmp_dir_name, sample,
                     file_name),
        os.path.join(tmp_dir, sample, file_name))
    bai_file_name = sam_bam.BAI_FORMAT.format(file_name)
    compare_files.compare_files(
        os.path.join(expected_fixture, tmp_dir_name, sample,
                     bai_file_name),
        os.path.join(tmp_dir, sample, bai_file_name))


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [workflow_files.DEDUP_BAM])
def test_dedup_samtools_index(dedup_umis, tmp_dir, sample, file_name):
    """
    Test that BAM and BI files exist.

    If UMI deduplication was not enabled in the configuration that
    produced the data then this test is skipped.

    :param dedup_umi: Was UMI deduplication configured?
    :type dedup_umis: bool
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    if not dedup_umis:
        pytest.skip('Skipped test applicable to UMI deduplication')
    assert os.path.exists(os.path.join(tmp_dir, sample, file_name))
    bai_file_name = sam_bam.BAI_FORMAT.format(file_name)
    assert os.path.exists(os.path.join(tmp_dir, sample, bai_file_name))


@pytest.mark.usefixtures("skip_index_tmp_fixture")
@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.PRE_DEDUP_GROUPS_TSV])
def test_umitools_group_tsv(group_umis, expected_fixture, tmp_dir,
                            sample, file_name):
    """
    Test ``umi_tools group`` TSV files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    If UMI grouping was not enabled in the configuration that
    produced the data then this test is skipped.

    :param dedup_umi: Was UMI grouping configured?
    :type dedup_umis: bool
    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param tmp_dir: Temporary directory, from configuration file
    :type tmp_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    if not group_umis:
        pytest.skip('Skipped test applicable to UMI groups')
    tmp_dir_name = os.path.basename(os.path.normpath(tmp_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, tmp_dir_name, sample,
                     file_name),
        os.path.join(tmp_dir, sample, file_name))


@pytest.mark.usefixtures("nextflow_fixture")
def test_samtools_view_sort_index_output(dedup_umis, expected_fixture,
                                         output_dir, sample):
    """
    Test ``samtools view | samtools sort`` BAM and ``samtools index``
    BAI files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    If UMI deduplication was enabled in the configuration that
    produced the data then this test is skipped.

    :param dedup_umi: Was UMI deduplication configured?
    :type dedup_umis: bool
    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param output_dir: Temporary directory, from configuration file
    :type output_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    """
    if dedup_umis:
        pytest.skip('Skipped test not applicable to UMI deduplication')
    output_dir_name = os.path.basename(os.path.normpath(output_dir))
    bam_file_name = sam_bam.BAM_FORMAT.format(sample)
    compare_files.compare_files(
        os.path.join(expected_fixture, output_dir_name, sample,
                     bam_file_name),
        os.path.join(output_dir, sample, bam_file_name))
    bai_file_name = sam_bam.BAI_FORMAT.format(bam_file_name)
    compare_files.compare_files(
        os.path.join(expected_fixture, output_dir_name, sample,
                     bai_file_name),
        os.path.join(output_dir, sample, bai_file_name))


@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name", [
    workflow_files.MINUS_BEDGRAPH,
    workflow_files.PLUS_BEDGRAPH])
def test_bedtools_bedgraph(expected_fixture, output_dir, sample,
                           file_name):
    """
    Test ``bedtools genomecov`` bedgraph files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param output_dir: Output directory, from configuration file
    :type output_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    output_dir_name = os.path.basename(os.path.normpath(output_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, output_dir_name, sample,
                     file_name),
        os.path.join(output_dir, sample, file_name))


@pytest.mark.usefixtures("nextflow_fixture")
def test_bam_to_h5_h5(expected_fixture, output_dir, sample):
    """
    Test ``bam_to_h5.R`` H5 files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param output_dir: Output directory, from configuration file
    :type output_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    """
    file_name = h5.H5_FORMAT.format(sample)
    output_dir_name = os.path.basename(os.path.normpath(output_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, output_dir_name, sample,
                     file_name),
        os.path.join(output_dir, sample, file_name))


@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name",
                         [workflow_r.THREE_NT_PERIODICITY_TSV,
                          workflow_r.CODON_RIBODENS_TSV,
                          workflow_r.POS_SP_NT_FREQ_TSV,
                          workflow_r.POS_SP_RPF_NORM_READS_TSV,
                          workflow_r.READ_LENGTHS_TSV,
                          workflow_r.THREE_NT_FRAME_BY_GENE_TSV,
                          workflow_r.TPMS_TSV])
def test_generate_stats_figs_tsv(expected_fixture, output_dir, sample,
                                 file_name):
    """
    Test ``generate_stats_figs.R`` TSV files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param output_dir: Output directory, from configuration file
    :type output_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    output_dir_name = os.path.basename(os.path.normpath(output_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, output_dir_name, sample,
                     file_name),
        os.path.join(output_dir, sample, file_name))


@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name",
                         [workflow_r.THREE_NT_PERIODICITY_PDF,
                          workflow_r.CODON_RIBODENS_PDF,
                          workflow_r.FEATURES_PDF,
                          workflow_r.POS_SP_RPF_NORM_READS_PDF,
                          workflow_r.READ_LENGTHS_PDF,
                          workflow_r.START_CODON_RIBOGRID_BAR_PDF,
                          workflow_r.START_CODON_RIBOGRID_PDF,
                          workflow_r.THREE_NT_FRAME_PROP_BY_GENE_PDF])
def test_generate_stats_figs_pdf(expected_fixture, output_dir, sample,
                                 file_name):
    """
    Test ``generate_stats_figs.R`` PDF files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param output_dir: Output directory, from configuration file
    :type output_dir: str or unicode
    :param sample: sample name
    :type sample: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    output_dir_name = os.path.basename(os.path.normpath(output_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, output_dir_name, sample,
                     file_name),
        os.path.join(output_dir, sample, file_name))


@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name",
                         [workflow_r.TPMS_COLLATED_TSV])
def test_collate_tpms_tsv(expected_fixture, output_dir, file_name):
    """
    Test ``collate_tpms.R`` TSV files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    Test non-sample-specific output TSV files for equality. See
    :py:func:`riboviz.compare_files.compare_files`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param output_dir: Output directory, from configuration file
    :type output_dir: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    output_dir_name = os.path.basename(os.path.normpath(output_dir))
    compare_files.compare_files(
        os.path.join(expected_fixture, output_dir_name, file_name),
        os.path.join(output_dir, file_name))


@pytest.mark.usefixtures("nextflow_fixture")
@pytest.mark.parametrize("file_name",
                         [workflow_files.READ_COUNTS_FILE])
def test_read_counts_tsv(expected_fixture, output_dir, file_name):
    """
    Test :py:mod:`riboviz.tools.count_reads` TSV files for
    equality. See :py:func:`riboviz.count_reads.equal_read_counts`.

    :param expected_fixture: Expected data directory
    :type expected_fixture: str or unicode
    :param output_dir: Output directory, from configuration file
    :type output_dir: str or unicode
    :param file_name: file name
    :type file_name: str or unicode
    """
    output_dir_name = os.path.basename(os.path.normpath(output_dir))
    count_reads.equal_read_counts(
        os.path.join(expected_fixture, output_dir_name, file_name),
        os.path.join(output_dir, file_name))
