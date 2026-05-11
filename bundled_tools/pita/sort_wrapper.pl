#!/usr/bin/perl
use strict;
my @lines = <STDIN>;
my ($key_field, $numeric) = (undef, 0);
foreach my $a (@ARGV) {
    if ($a =~ /^-k(\d+)n$/) { $key_field = $1 - 1; $numeric = 1; }
    elsif ($a =~ /^-k(\d+)/) { $key_field = $1 - 1; }
    elsif ($a eq '-n') { $numeric = 1; }
}
if (defined $key_field && $numeric) {
    @lines = sort { my @a=split/\t/,$a; my @b=split/\t/,$b; ($a[$key_field]//0)<=>($b[$key_field]//0) } @lines;
} elsif (defined $key_field) {
    @lines = sort { my @a=split/\t/,$a; my @b=split/\t/,$b; ($a[$key_field]//'') cmp ($b[$key_field]//'') } @lines;
} else {
    @lines = sort @lines;
}
print for @lines;
